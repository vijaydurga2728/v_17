from datetime import UTC, datetime

import numpy as np
import pandas as pd

from v17.setups.sessions import (
    asian_high_low,
    asian_range,
    in_judas_window,
    in_silver_bullet_window,
)


def test_sb_window_edt_summer() -> None:
    # 03:00 NY on 2024-06-05 (EDT UTC-4) = 07:00 UTC
    assert in_silver_bullet_window(datetime(2024, 6, 5, 7, 0, tzinfo=UTC)) is True
    assert in_silver_bullet_window(datetime(2024, 6, 5, 7, 59, tzinfo=UTC)) is True
    assert in_silver_bullet_window(datetime(2024, 6, 5, 8, 0, tzinfo=UTC)) is False


def test_sb_window_est_winter() -> None:
    # 03:00 NY on 2024-01-15 (EST UTC-5) = 08:00 UTC
    assert in_silver_bullet_window(datetime(2024, 1, 15, 8, 0, tzinfo=UTC)) is True
    assert in_silver_bullet_window(datetime(2024, 1, 15, 8, 59, tzinfo=UTC)) is True


def test_judas_window_bst() -> None:
    # 07:00-10:00 London BST = 06:00-09:00 UTC (London Open Killzone)
    assert in_judas_window(datetime(2024, 6, 5, 6, 0, tzinfo=UTC)) is True
    assert in_judas_window(datetime(2024, 6, 5, 8, 59, tzinfo=UTC)) is True
    assert in_judas_window(datetime(2024, 6, 5, 9, 0, tzinfo=UTC)) is False


def test_asian_range_utc_bounds() -> None:
    start, end = asian_range(datetime(2024, 6, 5, 8, 0, tzinfo=UTC))
    assert start == datetime(2024, 6, 4, 23, 0, tzinfo=UTC)
    assert end == datetime(2024, 6, 5, 6, 0, tzinfo=UTC)


def test_asian_high_low() -> None:
    ts = pd.date_range("2024-06-04 23:00", periods=420, freq="1min", tz="UTC")
    highs = np.linspace(1.100, 1.105, 420)
    lows = highs - 0.001
    df = pd.DataFrame(
        {
            "ts": ts,
            "open": highs - 0.0005,
            "high": highs,
            "low": lows,
            "close": highs - 0.0005,
            "volume": np.ones(420, dtype="int64"),
            "spread_pips": np.full(420, 0.8),
        }
    )
    hi, lo = asian_high_low(df, datetime(2024, 6, 5, 8, 0, tzinfo=UTC))
    assert hi == 1.105 and abs(lo - 1.099) < 1e-9
