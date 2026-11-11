"""Session VWAP tests."""
from __future__ import annotations

import pandas as pd

from v17.structure.vwap import compute_session_vwap


def _ts(mins: list[int]) -> list[int]:
    return [m * 60_000_000_000 for m in mins]


def test_vwap_cumulative_within_session_weighted_by_volume() -> None:
    bars = pd.DataFrame({
        "ts_ns": _ts([0, 1, 2, 3, 4]),
        "high":  [100.0, 100.5, 101.0, 100.8, 100.6],
        "low":   [99.5,  100.0, 100.3, 100.2, 100.1],
        "close": [99.8,  100.2, 100.7, 100.5, 100.4],
        "volume":[10, 20, 30, 10, 10],
    })
    vwap = compute_session_vwap(bars, session_start_ns=0, session_end_ns=_ts([4])[0])

    tp0 = (100.0 + 99.5 + 99.8) / 3
    tp1 = (100.5 + 100.0 + 100.2) / 3
    assert abs(vwap.iloc[0] - tp0) < 1e-9
    assert abs(vwap.iloc[1] - (tp0 * 10 + tp1 * 20) / 30) < 1e-9


def test_vwap_fallback_without_volume_column() -> None:
    bars = pd.DataFrame({
        "ts_ns": _ts([0, 1, 2]),
        "high":  [1.0, 2.0, 3.0],
        "low":   [0.5, 1.5, 2.5],
        "close": [0.8, 1.8, 2.8],
    })
    vwap = compute_session_vwap(bars, 0, _ts([2])[0])
    tp = (bars["high"] + bars["low"] + bars["close"]) / 3
    assert abs(vwap.iloc[2] - tp.mean()) < 1e-9


def test_vwap_nan_outside_session_window() -> None:
    bars = pd.DataFrame({
        "ts_ns": _ts([0, 1, 2, 3]),
        "high":  [1.0, 2.0, 3.0, 4.0],
        "low":   [0.5, 1.5, 2.5, 3.5],
        "close": [0.8, 1.8, 2.8, 3.8],
    })
    vwap = compute_session_vwap(bars, session_start_ns=_ts([1])[0], session_end_ns=_ts([2])[0])
    assert pd.isna(vwap.iloc[0])
    assert pd.isna(vwap.iloc[3])
    assert not pd.isna(vwap.iloc[1])
    assert not pd.isna(vwap.iloc[2])


def test_vwap_empty_slice_returns_all_nan() -> None:
    bars = pd.DataFrame({
        "ts_ns": _ts([0, 1]),
        "high": [1.0, 2.0], "low": [0.5, 1.5], "close": [0.8, 1.8],
    })
    vwap = compute_session_vwap(bars, session_start_ns=_ts([10])[0], session_end_ns=_ts([20])[0])
    assert vwap.isna().all()
