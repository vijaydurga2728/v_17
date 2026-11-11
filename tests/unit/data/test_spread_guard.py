import pandas as pd
import numpy as np
from v17.data.spread_guard import SpreadGuard


def test_rejects_when_spread_above_3x_median():
    ts = pd.date_range("2024-01-01", periods=35 * 1440, freq="min", tz="UTC").astype("int64")
    spread = np.full(len(ts), 1.0)
    bars = pd.DataFrame({"ts_utc": ts, "symbol": "X", "spread_mid": spread})
    guard = SpreadGuard(bars, symbol="X")
    probe = int(pd.Timestamp("2024-02-04 10:00:00", tz="UTC").value)
    assert guard.should_reject(probe, current_spread=5.0) is True
    assert guard.should_reject(probe, current_spread=2.5) is False


def test_returns_false_with_insufficient_history():
    ts = pd.date_range("2024-01-01", periods=10, freq="min", tz="UTC").astype("int64")
    bars = pd.DataFrame({"ts_utc": ts, "symbol": "X", "spread_mid": [1.0] * len(ts)})
    guard = SpreadGuard(bars, symbol="X")
    probe = int(pd.Timestamp("2024-01-05 10:00:00", tz="UTC").value)
    # Minute-of-day 10:00 unseen → False
    assert guard.should_reject(probe, current_spread=100.0) is False


def test_minute_of_day_bucket_separation():
    # Two spreads at different minutes-of-day: queries must bucket by minute
    ts = pd.date_range("2024-01-01", periods=35 * 1440, freq="min", tz="UTC").astype("int64")
    pd_ts = pd.to_datetime(ts, utc=True)
    spread = np.where(pd_ts.hour == 10, 1.0, 100.0).astype(float)
    bars = pd.DataFrame({"ts_utc": ts, "symbol": "X", "spread_mid": spread})
    guard = SpreadGuard(bars, symbol="X")
    probe = int(pd.Timestamp("2024-02-04 10:00:00", tz="UTC").value)
    # Median at 10:00 is 1.0, so 3.0 current → 3x median exactly, NOT > 3x → False
    assert guard.should_reject(probe, current_spread=3.0) is False
    # 3.5 > 3.0 → True
    assert guard.should_reject(probe, current_spread=3.5) is True
