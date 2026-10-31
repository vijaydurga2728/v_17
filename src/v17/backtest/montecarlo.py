from __future__ import annotations

from decimal import Decimal
from typing import TypedDict

import numpy as np

from v17.backtest.metrics import max_drawdown_pct, profit_factor


class MCResult(TypedDict):
    p5_pf: float
    p95_max_dd_pct: float
    mean_pf: float
    mean_max_dd_pct: float
    n: int


def _equity_from_pnls(pnls: list[Decimal], starting: Decimal = Decimal("100000")) -> list[Decimal]:
    eq = [starting]
    for p in pnls:
        eq.append(eq[-1] + p)
    return eq


def _permute_once(pnls: list[Decimal], rng: np.random.Generator) -> list[Decimal]:
    idx = rng.permutation(len(pnls))
    return [pnls[int(i)] for i in idx]


def _block_bootstrap_once(
    pnls: list[Decimal], block: int, rng: np.random.Generator
) -> list[Decimal]:
    n = len(pnls)
    out: list[Decimal] = []
    while len(out) < n:
        start = int(rng.integers(0, max(1, n - block + 1)))
        out.extend(pnls[start : start + block])
    return out[:n]


def hybrid_mc(
    trade_pnls: list[Decimal],
    seed: int,
    perm_runs: int = 500,
    boot_runs: int = 500,
    block: int = 5,
) -> MCResult:
    if not trade_pnls:
        return MCResult(p5_pf=0.0, p95_max_dd_pct=0.0, mean_pf=0.0, mean_max_dd_pct=0.0, n=0)
    rng = np.random.default_rng(seed)
    pfs: list[float] = []
    dds: list[float] = []
    for _ in range(perm_runs):
        permuted = _permute_once(trade_pnls, rng)
        pfs.append(profit_factor(permuted))
        dds.append(max_drawdown_pct(_equity_from_pnls(permuted)))
    for _ in range(boot_runs):
        sampled = _block_bootstrap_once(trade_pnls, block, rng)
        pfs.append(profit_factor(sampled))
        dds.append(max_drawdown_pct(_equity_from_pnls(sampled)))
    pf_arr = np.array(pfs, dtype="float64")
    dd_arr = np.array(dds, dtype="float64")
    # drop infs from PF for percentile stability
    pf_finite = pf_arr[np.isfinite(pf_arr)]
    if len(pf_finite) == 0:
        pf_finite = np.zeros(1)
    return MCResult(
        p5_pf=float(np.percentile(pf_finite, 5)),
        p95_max_dd_pct=float(np.percentile(dd_arr, 95)),
        mean_pf=float(pf_finite.mean()),
        mean_max_dd_pct=float(dd_arr.mean()),
        n=perm_runs + boot_runs,
    )
