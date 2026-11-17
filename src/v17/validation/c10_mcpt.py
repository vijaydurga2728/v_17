"""Cycle 10 MCPT: direction-permutation null (pre-reg §10 Tier 2, decision Q-B).

Every trade keeps its entry/exit timestamps. The observed vector of trade
directions is randomly permuted (exact long/short counts preserved) and each
trade's net R is taken from its precomputed long or short outcome at the same
timestamps with real bid/ask. Fixed N_PERMS permutations, plus-one p-value.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from v17.setups.c10_intraday_momentum import SLOTS, TradeArrays

BASE_SEED = 20261117
N_PERMS = 100_000
HOLDOUT_SEED_OFFSET = 500


def slot_seed(slot: str, holdout: bool = False) -> int:
    return BASE_SEED * 1_000 + (HOLDOUT_SEED_OFFSET if holdout else 0) + SLOTS.index(slot)


@dataclass(frozen=True)
class MCPTResult:
    p_value: float
    n_perms: int
    exceedances: int
    observed_mean_r: float


def run_mcpt(tr: TradeArrays, slot: str, *, holdout: bool = False,
             n_perms: int = N_PERMS) -> tuple[MCPTResult, pd.DataFrame]:
    if len(tr.side) == 0:
        raise ValueError("no trades: MCPT undefined")
    seed = slot_seed(slot, holdout)
    is_long = tr.side == 1
    observed = float(tr.r.mean())
    null = np.empty(n_perms)
    hashes: list[str] = []
    for j in range(n_perms):
        perm = np.random.default_rng([seed, j]).permutation(is_long)
        null[j] = float(np.where(perm, tr.r_long, tr.r_short).mean())
        hashes.append(hashlib.blake2b(np.packbits(perm).tobytes(), digest_size=8).hexdigest())
    e = int((null >= observed).sum())
    log = pd.DataFrame({"perm": np.arange(n_perms), "seed": seed, "dirs_hash": hashes,
                        "n_long": int(is_long.sum()), "mean_r_null": null})
    return MCPTResult((e + 1) / (n_perms + 1), n_perms, e, observed), log
