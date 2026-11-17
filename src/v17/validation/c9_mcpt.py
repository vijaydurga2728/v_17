"""Cycle 9 scheme-1 MCPT: session-aligned block bootstrap, fixed permutation count.

Spec: ADR 001 Correction A as amended by ADR 002 (rev 2) Corrections I, J, K.

- Null path (ADR 002 I): session 0 is the fixed anchor; sessions 1..K-1 are
  whole real sessions drawn with replacement from the pool {1..K-1}. Each
  block carries its own overnight gap return. Mid closes are re-chained from
  the anchor; every OHLC bid/ask/mid field is translated by the same per-bar
  shift (source-bar geometry). Calendar labels (dates, prev_ok) stay real.
- PDH/PDL and ATR are recomputed on the synthetic path; the full strategy is
  rerun. Statistic: mean R (0 when no synthetic trades).
- p-value (ADR 002 J rev 2 = ADR 001 A.2): fixed N_PERMS permutations, always
  all of them; p = (count(null_mean_r >= observed_mean_r) + 1) / (N_PERMS + 1).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from v17.setups.c9_pdh_pdl import (
    PRICE_FIELDS,
    Sessions,
    Slot,
    all_slots,
    atr_prev,
    levels,
    simulate_raw,
)

BASE_SEED = 20261116
N_PERMS = 100_000
HOLDOUT_SEED_OFFSET = 500


def slot_seed(slot: Slot, holdout: bool = False) -> int:
    """ADR 001 A.3 (dev) / ADR 002 K (holdout)."""
    idx = all_slots().index(slot)
    return BASE_SEED * 1_000 + (HOLDOUT_SEED_OFFSET if holdout else 0) + idx


@dataclass(frozen=True)
class MCPTResult:
    p_value: float
    n_perms: int
    exceedances: int


def fixed_count_p(exceedances: int, n_perms: int) -> float:
    """ADR 001 A.2 plus-one p-value."""
    if not 0 <= exceedances <= n_perms or n_perms <= 0:
        raise ValueError("need 0 <= exceedances <= n_perms and n_perms > 0")
    return (exceedances + 1) / (n_perms + 1)


class SessionPool:
    """Precomputed per-session quantities for fast synthetic path generation."""

    def __init__(self, sess: Sessions) -> None:
        if sess.n_sessions < 3:
            raise ValueError("need >= 3 sessions for the session bootstrap")
        self.sess = sess
        off = sess.offsets
        mc = sess["mid_c"]
        self.lens = np.diff(off)
        self.first = off[:-1]
        self.last_mc = mc[off[1:] - 1]
        self.prev_last_mc = np.r_[np.nan, self.last_mc[:-1]]  # pool excludes session 0
        self.n0 = int(self.lens[0])

    def synthetic(self, draw: np.ndarray) -> Sessions:
        """Build the synthetic Sessions for block draw ``draw`` (len K-1, values in 1..K-1)."""
        s = self.sess
        lens = self.lens[draw]
        block_id = np.repeat(np.arange(len(draw)), lens)
        within = np.arange(int(lens.sum())) - np.repeat(np.cumsum(lens) - lens, lens)
        src = self.first[draw][block_id] + within
        ratio = self.last_mc[draw] / self.prev_last_mc[draw]
        anchor = self.last_mc[0] * np.r_[1.0, np.cumprod(ratio)[:-1]]
        mc_src = s["mid_c"][src]
        mc_perm = anchor[block_id] * mc_src / self.prev_last_mc[draw][block_id]
        shift = mc_perm - mc_src
        prices = {}
        for f in PRICE_FIELDS:
            x = s[f]
            prices[f] = np.r_[x[: self.n0], x[src] + shift]
        offsets = np.r_[0, self.n0 + np.r_[0, np.cumsum(lens)]].astype(np.int64)
        bins = np.r_[s.bins[: self.n0], s.bins[src]]
        return Sessions(s.dates, offsets, bins, prices, s.prev_ok)


def mean_r_of(sess: Sessions, slot: Slot, slippage_pts: float) -> tuple[float, int]:
    pdh, pdl = levels(sess)
    _, fout = simulate_raw(sess, pdh, pdl, atr_prev(sess), slot, slippage_pts)
    n = len(fout)
    return (float(fout[:, 4].mean()) if n else 0.0), n


def run_mcpt(
    sess: Sessions, slot: Slot, *, slippage_pts: float = 0.0, holdout: bool = False,
    n_perms: int = N_PERMS,
) -> tuple[MCPTResult, float, pd.DataFrame]:
    """Run exactly ``n_perms`` permutations (no early stopping).

    Returns (result, observed_mean_r, per-permutation log). Callers running a gate
    must use the default ``n_perms`` (ADR 001 A.1); smaller values exist for tests.
    """
    observed, _ = mean_r_of(sess, slot, slippage_pts)
    pool = SessionPool(sess)
    seed = slot_seed(slot, holdout)
    k = sess.n_sessions
    null = np.empty(n_perms)
    n_tr = np.empty(n_perms, dtype=np.int64)
    hashes: list[str] = []
    for j in range(n_perms):
        draw = np.random.default_rng([seed, j]).integers(1, k, size=k - 1)
        null[j], n_tr[j] = mean_r_of(pool.synthetic(draw), slot, slippage_pts)
        hashes.append(hashlib.blake2b(draw.tobytes(), digest_size=8).hexdigest())
    e = int((null >= observed).sum())
    log = pd.DataFrame({"perm": np.arange(n_perms), "seed": seed, "blocks_hash": hashes,
                        "n_trades_null": n_tr, "mean_r_null": null})
    return MCPTResult(fixed_count_p(e, n_perms), n_perms, e), observed, log
