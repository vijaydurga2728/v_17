"""Paired bid/ask M1 → H1 resample tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.common.types import TF
from v17.data.resample import resample_paired


def _m1(n: int, start_ns: int = 0) -> pd.DataFrame:
    ts = start_ns + np.arange(n, dtype=np.int64) * 60_000_000_000
    return pd.DataFrame({
        "ts_utc": ts,
        "symbol": ["EURUSD"] * n,
        "bid_o": np.full(n, 1.1000) + np.arange(n) * 0.0001,
        "bid_h": np.full(n, 1.1002) + np.arange(n) * 0.0001,
        "bid_l": np.full(n, 1.0998) + np.arange(n) * 0.0001,
        "bid_c": np.full(n, 1.1001) + np.arange(n) * 0.0001,
        "ask_o": np.full(n, 1.1001) + np.arange(n) * 0.0001,
        "ask_h": np.full(n, 1.1003) + np.arange(n) * 0.0001,
        "ask_l": np.full(n, 1.0999) + np.arange(n) * 0.0001,
        "ask_c": np.full(n, 1.1002) + np.arange(n) * 0.0001,
        "bid_volume": np.full(n, 1.0),
        "ask_volume": np.full(n, 1.0),
        "spread_mid": np.full(n, 0.0001),
    })


def test_h1_aggregates_60_m1_bars() -> None:
    df = _m1(120)  # exactly 2 H1 bars
    h1 = resample_paired(df, TF.H1)
    assert len(h1) == 2
    # Bar 0 covers M1 indices 0..59
    assert abs(h1["bid_o"].iloc[0] - 1.1000) < 1e-9
    assert abs(h1["bid_h"].iloc[0] - (1.1002 + 59 * 0.0001)) < 1e-9
    assert abs(h1["bid_l"].iloc[0] - 1.0998) < 1e-9
    assert abs(h1["bid_c"].iloc[0] - (1.1001 + 59 * 0.0001)) < 1e-9
    assert h1["bid_volume"].iloc[0] == 60.0
    assert h1["ask_volume"].iloc[0] == 60.0
    assert abs(h1["spread_mid"].iloc[0] - 0.0001) < 1e-9


def test_h1_schema_preserved() -> None:
    df = _m1(60)
    h1 = resample_paired(df, TF.H1)
    assert list(h1.columns) == [
        "ts_utc", "symbol",
        "bid_o", "bid_h", "bid_l", "bid_c",
        "ask_o", "ask_h", "ask_l", "ask_c",
        "bid_volume", "ask_volume", "spread_mid",
    ]
    assert h1["ts_utc"].dtype == np.int64


def test_m1_passthrough() -> None:
    df = _m1(10)
    out = resample_paired(df, TF.M1)
    pd.testing.assert_frame_equal(out.reset_index(drop=True), df.reset_index(drop=True))


def test_partial_window_dropped_only_when_no_data() -> None:
    df = _m1(75)  # 1 full H1 + 15 M1 into next H1
    h1 = resample_paired(df, TF.H1)
    assert len(h1) == 2
    assert h1["bid_volume"].iloc[1] == 15.0
