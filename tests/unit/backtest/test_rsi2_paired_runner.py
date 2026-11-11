"""Paired-alpha runner tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.backtest.rsi2_paired_runner import _mark_active, _alpha_metrics


_D1_NS = 86_400_000_000_000


def _ts_series(n: int, start="2015-01-01") -> np.ndarray:
    base = pd.Timestamp(start, tz="UTC").value
    return base + np.arange(n, dtype=np.int64) * _D1_NS


def test_mark_active_marks_in_trade_bars():
    ts = _ts_series(10)
    trades = [
        {"ts_entry_ns": int(ts[2]), "ts_exit_ns": int(ts[4])},
        {"ts_entry_ns": int(ts[7]), "ts_exit_ns": int(ts[8])},
    ]
    active = _mark_active(trades, ts, int(ts[0]), int(ts[-1] + _D1_NS))
    expected = np.array([False, False, True, True, True, False, False, True, True, False])
    assert np.array_equal(active, expected)


def test_alpha_zero_when_exposure_matches_full_coverage():
    """Edge case: if active_pos==1 on all in-window bars, alpha=0."""
    ts = _ts_series(10)
    log_ret = np.full(10, 0.01)
    active = np.ones(10, dtype=bool)
    in_window = np.ones(10, dtype=bool)
    m = _alpha_metrics(active, log_ret, in_window)
    assert m is not None
    assert abs(m.observed_alpha_cum) < 1e-9


def test_alpha_positive_when_active_days_have_higher_return():
    """Signal-aligned days have higher returns -> positive alpha."""
    ts = _ts_series(20)
    log_ret = np.where(np.arange(20) % 2 == 0, 0.02, 0.0)  # even days +2%, odd 0
    active = np.zeros(20, dtype=bool)
    active[np.arange(0, 20, 2)] = True  # active on even days
    in_window = np.ones(20, dtype=bool)
    m = _alpha_metrics(active, log_ret, in_window)
    assert m is not None
    assert m.observed_alpha_cum > 0
    assert m.observed_alpha_mean > 0
    assert m.observed_alpha_pf > 1.0


def test_alpha_negative_when_active_misses_the_good_days():
    """Signal lands on bad days -> negative alpha."""
    ts = _ts_series(20)
    log_ret = np.where(np.arange(20) % 2 == 0, 0.02, 0.0)
    active = np.zeros(20, dtype=bool)
    active[np.arange(1, 20, 2)] = True  # active on ODD (zero-return) days
    in_window = np.ones(20, dtype=bool)
    m = _alpha_metrics(active, log_ret, in_window)
    assert m is not None
    assert m.observed_alpha_cum < 0
