import numpy as np
import pandas as pd

from v17.backtest.c6_grid import run_grid


def _mk_series(n_days: int, trend: float, pair: str):
    from tests.integration.test_c6_runner import _synthetic_m5
    return _synthetic_m5(n_days, trend, pair)


def test_grid_runs_all_48_configs_small_dev():
    spx = _mk_series(10, 0.05, "USA500IDXUSD")
    aud = _mk_series(10, 0.05, "AUDUSD")
    jpy = _mk_series(10, 0.05, "USDJPY")
    cal = pd.DataFrame({"ts_utc": [], "currency": [], "impact": [], "title": []})
    grid = run_grid(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal,
                    start_ts_ns=spx["ts_utc"].min(), end_ts_ns=spx["ts_utc"].max(),
                    equity=10_000.0)
    assert len(grid) == 48
    assert set(["K", "slope_window", "C", "sharpe", "pf", "trade_count"]).issubset(grid.columns)
