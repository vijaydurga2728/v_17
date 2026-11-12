"""Cycle 6 paired-alpha ablation nulls: random, regime-only, micro-only."""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from v17.validation.c6_gates import _sharpe_from_trades


def paired_alpha(obs_tl: pd.DataFrame, null_tl: pd.DataFrame, seed: int, n_bootstrap: int = 1000) -> float:
    rng = np.random.default_rng(seed)
    obs_pnl = obs_tl["net_pnl_usd"].to_numpy()
    null_pnl = null_tl["net_pnl_usd"].to_numpy()
    obs_sharpe = _sharpe_from_trades(obs_pnl)
    null_sharpe = _sharpe_from_trades(null_pnl)
    diff_obs = obs_sharpe - null_sharpe
    pooled = np.concatenate([obs_pnl, null_pnl])
    n_o, n_n = len(obs_pnl), len(null_pnl)
    diffs = np.empty(n_bootstrap, dtype=float)
    for i in range(n_bootstrap):
        perm = rng.permutation(pooled)
        a, b = perm[:n_o], perm[n_o:n_o + n_n]
        diffs[i] = _sharpe_from_trades(a) - _sharpe_from_trades(b)
    p = float((diffs >= diff_obs).sum() + 1) / (n_bootstrap + 1)
    return p


def null_random_entries(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    params: dict,
    equity: float,
    n_trades_per_sym_dir: dict,
    seed: int,
) -> pd.DataFrame:
    """Null-A: sample random M5 entry bars per (symbol, direction) matching observed counts.

    Exits follow the normal position state-machine. Returns a trade log in same schema.
    """
    raise NotImplementedError("Wired in Task 15 driver where override callback lives.")


def null_regime_only(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    params: dict,
    equity: float,
    seed: int,
) -> pd.DataFrame:
    raise NotImplementedError("Wired in Task 15 driver.")


def null_micro_only(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    params: dict,
    equity: float,
    seed: int,
) -> pd.DataFrame:
    raise NotImplementedError("Wired in Task 15 driver.")
