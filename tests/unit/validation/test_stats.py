import numpy as np
import pandas as pd
import pytest
from v17.validation.stats import compute_stats


def test_stats_on_known_series():
    pnls = np.array([1.0, -0.5, 1.0, -0.5, 1.0])
    ts = pd.date_range("2024-01-01", periods=5, freq="D", tz="UTC").astype("int64").to_numpy()
    s = compute_stats(pnls, ts)
    assert s.pf == pytest.approx(3.0)
    assert s.trade_count == 5
    assert 0.5 < s.win_rate < 0.7
    assert s.max_dd >= 0


def test_empty_series():
    s = compute_stats(np.array([]), np.array([]))
    assert s.trade_count == 0
    assert s.sharpe == 0.0
    assert s.pf == 0.0 or s.pf == float("inf")


def test_all_wins_infinite_pf():
    s = compute_stats(np.array([1.0, 1.0, 1.0]), np.arange(3))
    assert s.pf == float("inf")


def test_r2_positive_for_linear_equity():
    pnls = np.array([1.0] * 10)  # perfectly linear cumulative
    s = compute_stats(pnls, np.arange(10))
    assert s.r2 > 0.99


def test_max_dd_captured():
    pnls = np.array([1.0, 1.0, -2.0, -1.0, 1.0])
    s = compute_stats(pnls, np.arange(5))
    # equity: 1, 2, 0, -1, 0; peak 2; max dd = 2 - (-1) = 3
    assert s.max_dd == pytest.approx(3.0)
