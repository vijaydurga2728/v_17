"""Scheme-1 MCPT for Cycle 6."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from v17.validation.c6_gates import _sharpe_from_trades


def scheme1_mcpt(
    trade_log: pd.DataFrame,
    run_null: Callable[[int], pd.DataFrame],
    n_permutations: int,
    seed: int,
) -> dict:
    obs_sharpe = _sharpe_from_trades(trade_log["net_pnl_usd"].to_numpy())
    null_sharpes = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        null_tl = run_null(i)
        null_sharpes[i] = _sharpe_from_trades(null_tl["net_pnl_usd"].to_numpy())
    p = float((null_sharpes >= obs_sharpe).sum() + 1) / (n_permutations + 1)
    return {
        "observed_sharpe": obs_sharpe,
        "null_sharpe_mean": float(null_sharpes.mean()),
        "null_sharpe_p95": float(np.percentile(null_sharpes, 95)),
        "p_sharpe": p,
    }
