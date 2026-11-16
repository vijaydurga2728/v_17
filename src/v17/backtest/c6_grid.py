"""Cycle 6 grid search over (K, slope_window, C)."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Mapping

import pandas as pd

from v17.backtest.c6_runner import run_backtest
from v17.setups.c6_constants import CONFIRM_BODY_GRID, K_GRID, SLOPE_WINDOW_GRID
from v17.validation.c6_gates import compute_metrics

_PROGRESS_PATH = Path(os.environ.get("V17_GRID_PROGRESS", "out/c6/dev_grid.progress"))


def _log_progress(msg: str) -> None:
    _PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _PROGRESS_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")


def run_grid(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    start_ts_ns: int,
    end_ts_ns: int,
    equity: float,
) -> pd.DataFrame:
    """Run backtest for all 48 (K, slope_window, C) combinations.

    Returns a DataFrame with one row per config and columns:
    K, slope_window, C, sharpe, pf, trade_count, max_daily_loss_pct, max_consec_losing_days.
    """
    rows = []
    total = len(K_GRID) * len(SLOPE_WINDOW_GRID) * len(CONFIRM_BODY_GRID)
    i = 0
    t_start = time.time()
    _log_progress(f"START grid total={total}")
    for K in K_GRID:
        for sw in SLOPE_WINDOW_GRID:
            for C in CONFIRM_BODY_GRID:
                i += 1
                t0 = time.time()
                _log_progress(f"[grid {i}/{total}] START K={K} sw={sw} C={C} elapsed={time.time()-t_start:.1f}s")
                tl, ec = run_backtest(
                    spx_m5, fx_m5_by_sym, calendar_idx,
                    params={"K": K, "slope_window": sw, "C": C},
                    initial_equity=equity,
                    start_ts_ns=start_ts_ns,
                    end_ts_ns=end_ts_ns,
                )
                m = compute_metrics(tl, ec)
                dt = time.time() - t0
                _log_progress(f"[grid {i}/{total}] END K={K} sw={sw} C={C} trades={m['trade_count']} sharpe={m['sharpe']:.3f} took={dt:.1f}s")
                rows.append({
                    "K": K,
                    "slope_window": sw,
                    "C": C,
                    "sharpe": m["sharpe"],
                    "pf": m["pf"],
                    "trade_count": m["trade_count"],
                    "max_daily_loss_pct": m["max_daily_loss_pct"],
                    "max_consec_losing_days": m["max_consec_losing_days"],
                })
    return pd.DataFrame(rows)
