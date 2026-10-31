import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from v17.common.types import TF
from v17.structure.fvg import detect_fvgs


@st.composite
def ohlc_frame(draw: st.DrawFn, min_bars: int = 20, max_bars: int = 80) -> pd.DataFrame:
    n = draw(st.integers(min_value=min_bars, max_value=max_bars))
    ts = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    drifts = draw(
        st.lists(st.floats(-0.001, 0.001, allow_nan=False), min_size=n, max_size=n)
    )
    base = 1.10 + np.cumsum(drifts)
    hi_add = np.abs(
        np.array(
            draw(st.lists(st.floats(0.0, 0.0005, allow_nan=False), min_size=n, max_size=n))
        )
    )
    lo_sub = np.abs(
        np.array(
            draw(st.lists(st.floats(0.0, 0.0005, allow_nan=False), min_size=n, max_size=n))
        )
    )
    highs = base + hi_add
    lows = base - lo_sub
    opens = base
    close_wig = np.array(
        draw(st.lists(st.floats(-0.0003, 0.0003, allow_nan=False), min_size=n, max_size=n))
    )
    closes = base + close_wig
    # keep ohlc invariants: clamp close inside [low, high]
    closes = np.minimum(np.maximum(closes, lows), highs)
    opens = np.minimum(np.maximum(opens, lows), highs)
    return pd.DataFrame(
        {
            "ts": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n, dtype="int64"),
            "spread_pips": np.full(n, 0.8),
        }
    )


@settings(deadline=None, max_examples=20)
@given(ohlc_frame())
def test_fvg_zones_have_top_gt_bottom(df: pd.DataFrame) -> None:
    for z in detect_fvgs(df, TF.M15):
        assert z.top > z.bottom


@settings(deadline=None, max_examples=20)
@given(ohlc_frame())
def test_fvg_zones_timestamps_utc(df: pd.DataFrame) -> None:
    for z in detect_fvgs(df, TF.M15):
        assert z.created_at.tzinfo is not None
