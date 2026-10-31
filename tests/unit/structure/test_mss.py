from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd

from v17.common.dtos import Zone
from v17.common.types import TF, Side
from v17.structure.mss import detect_mss


def _1m_frame_with_bullish_choch() -> pd.DataFrame:
    # 60 1m bars: downtrend then sharp uptrend creating CHoCH with strong body
    n = 60
    ts = pd.date_range("2024-06-01", periods=n, freq="1min", tz="UTC")
    down = np.linspace(1.10050, 1.09950, 30)
    up = np.linspace(1.09950, 1.10100, 30)
    base = np.concatenate([down, up])
    opens = base.copy()
    closes = base.copy()
    # inject a strong-body bullish candle at bar 32 to trigger body > 1.5*ATR
    closes[32] = opens[32] + 0.0020
    highs = np.maximum(opens, closes) + 0.0001
    lows = np.minimum(opens, closes) - 0.0001
    return pd.DataFrame(
        {
            "ts": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n, dtype="int64"),
            "spread_pips": np.full(n, 0.3),
        }
    )


def test_detect_mss_in_zone() -> None:
    df = _1m_frame_with_bullish_choch()
    # zone that covers the choch area
    zone = Zone(
        kind="fvg",
        side=Side.BUY,
        tf=TF.M15,
        created_at=datetime(2024, 6, 1, tzinfo=UTC),
        top=Decimal("1.1100"),
        bottom=Decimal("1.0980"),
    )
    mss_list = detect_mss(df, [zone], atr_mult=1.5)
    assert all(s.kind == "mss" for s in mss_list)


def test_detect_mss_outside_zone_empty() -> None:
    df = _1m_frame_with_bullish_choch()
    # zone far away from current price
    zone = Zone(
        kind="fvg",
        side=Side.BUY,
        tf=TF.M15,
        created_at=datetime(2024, 6, 1, tzinfo=UTC),
        top=Decimal("1.2000"),
        bottom=Decimal("1.1900"),
    )
    mss_list = detect_mss(df, [zone], atr_mult=1.5)
    assert mss_list == []
