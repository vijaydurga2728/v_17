"""MCPT runner — single-scheme (block bootstrap) harness (spec section 7).

Amended 2026-11-04 (Audit 3 outcome, user-approved policy B): scheme 1
"signal_time" is DEFERRED. The current `permute_signal_time` only relabels
entry timestamps; it does not re-run the engine against permuted ts, so
`pnl_r` never changes and the null collapses to the observed value.
Calling `run_mcpt(..., scheme="signal_time", ...)` now raises `NotImplementedError`
to prevent silent no-op gates. Scheme 2 (pnl_bootstrap) is the sole active scheme.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from v17.validation.mcpt import block_bootstrap_pnl
from v17.validation.seeds import permutation_seed
from v17.validation.stats import compute_stats


_BLOCK_SIZE = 5  # approximation of one trading week; see spec section 7.1 amendment


def run_mcpt(
    engine_id: str,
    trades: pd.DataFrame,
    bars: pd.DataFrame,
    calendar: pd.DataFrame,
    scheme: str,
    n_permutations: int,
    out_root: Path,
) -> dict:
    pnls = trades["pnl_r"].to_numpy()
    ts = trades["ts_entry_ns"].to_numpy()
    observed = compute_stats(pnls, ts)

    if scheme == "signal_time":
        raise NotImplementedError(
            "scheme='signal_time' is DEFERRED per spec section 7 amendment (2026-11-04). "
            "Audit 3 MF-1/MF-2 flagged the current permute_signal_time as a no-op: "
            "it only relabels ts_entry_ns and never recomputes pnl_r against permuted "
            "timestamps. A correct implementation requires engine re-run on each "
            "permuted timestamp set (not implemented). Use scheme='pnl_bootstrap' only."
        )
    if scheme != "pnl_bootstrap":
        raise ValueError(f"Unknown scheme: {scheme!r}")

    rows: list[dict] = []
    for i in range(n_permutations):
        seed = permutation_seed(engine_id, scheme, i)
        permuted = block_bootstrap_pnl(pnls, block_size=_BLOCK_SIZE, seed=seed)
        s = compute_stats(permuted, ts)
        rows.append({
            "perm_idx": i,
            "sharpe": s.sharpe,
            "pf": s.pf if np.isfinite(s.pf) else float("nan"),
            "max_dd": s.max_dd,
            "r2": s.r2,
            "trade_count": s.trade_count,
        })

    df = pd.DataFrame(rows)
    out = Path(out_root) / "mcpt" / engine_id / scheme / "permutations.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)

    p_sharpe = float((df["sharpe"] >= observed.sharpe).mean())
    # Filter out non-finite PF before comparison
    finite_pf = df["pf"].dropna()
    if np.isfinite(observed.pf) and len(finite_pf) > 0:
        p_pf = float((finite_pf >= observed.pf).mean())
    else:
        p_pf = float("nan")

    return {
        "engine_id": engine_id,
        "scheme": scheme,
        "observed_sharpe": observed.sharpe,
        "observed_pf": observed.pf,
        "p_sharpe": p_sharpe,
        "p_pf": p_pf,
        "n_permutations": n_permutations,
    }
