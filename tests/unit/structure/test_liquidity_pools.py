import pandas as pd
import numpy as np
from v17.structure.liquidity_pools import enumerate_pools


def test_session_extreme_from_premarket_to_window_start():
    ts_range = pd.date_range("2024-03-15 05:00", "2024-03-15 15:00", freq="min", tz="UTC")
    n = len(ts_range)
    bars = pd.DataFrame({
        "ts_utc": ts_range.astype("int64"),
        "bid_h": [1.08 + i * 0.00001 for i in range(n)],
        "bid_l": [1.07 - i * 0.00001 for i in range(n)],
    })
    window_start_ns = int(pd.Timestamp("2024-03-15 14:00:00", tz="UTC").value)
    now_ns = window_start_ns + 60_000_000_000
    pools = enumerate_pools(bars, window_start_ns=window_start_ns, now_ns=now_ns)
    kinds = {p["kind"] for p in pools}
    assert "session_high" in kinds
    assert "session_low" in kinds


def test_prev_hour_pool_within_window():
    ts_range = pd.date_range("2024-03-15 12:00", "2024-03-15 14:30", freq="min", tz="UTC")
    n = len(ts_range)
    bars = pd.DataFrame({
        "ts_utc": ts_range.astype("int64"),
        "bid_h": [1.10 + i * 0.00001 for i in range(n)],
        "bid_l": [1.09 - i * 0.00001 for i in range(n)],
    })
    window_start_ns = int(pd.Timestamp("2024-03-15 14:00:00", tz="UTC").value)
    now_ns = window_start_ns + 1
    pools = enumerate_pools(bars, window_start_ns=window_start_ns, now_ns=now_ns)
    kinds = {p["kind"] for p in pools}
    assert "prev_hour_high" in kinds
    assert "prev_hour_low" in kinds


def test_no_asian_fallback_kind_emitted():
    bars = pd.DataFrame({"ts_utc": [1], "bid_h": [1.0], "bid_l": [1.0]})
    pools = enumerate_pools(bars, window_start_ns=2, now_ns=3)
    for p in pools:
        assert "asian" not in p["kind"].lower()


def test_empty_pre_window_returns_no_session_pools():
    # All bars at or after window_start
    ts = pd.date_range("2024-03-15 14:00", "2024-03-15 15:00", freq="min", tz="UTC")
    bars = pd.DataFrame({
        "ts_utc": ts.astype("int64"),
        "bid_h": [1.0] * len(ts),
        "bid_l": [1.0] * len(ts),
    })
    window_start_ns = int(pd.Timestamp("2024-03-15 14:00:00", tz="UTC").value)
    now_ns = window_start_ns + 60_000_000_000
    pools = enumerate_pools(bars, window_start_ns=window_start_ns, now_ns=now_ns)
    kinds = {p["kind"] for p in pools}
    assert "session_high" not in kinds
    assert "session_low" not in kinds
