import pandas as pd
import numpy as np
from v17.structure.fvg_sb import detect_fvgs_at


def _bars(highs, lows, opens=None, closes=None):
    n = len(highs)
    if opens is None:
        opens = [(h + l) / 2 for h, l in zip(highs, lows)]
    if closes is None:
        closes = opens[:]
    ts = pd.date_range("2024-01-01 09:00", periods=n, freq="min", tz="UTC").astype("int64")
    return pd.DataFrame({
        "ts_utc": ts,
        "bid_o": opens, "bid_h": highs, "bid_l": lows, "bid_c": closes,
        "ask_o": opens, "ask_h": highs, "ask_l": lows, "ask_c": closes,
    })


def test_bullish_fvg_detected_at_bar_i_only_uses_bars_up_to_i():
    df = _bars([1.00, 1.02, 1.03], [0.99, 1.00, 1.01])
    # as_of after bar 2 (strictly after its timestamp)
    as_of = int(df.iloc[2]["ts_utc"]) + 1
    fvgs = detect_fvgs_at(df, as_of_ns=as_of)
    bull = [f for f in fvgs if f["kind"] == "bullish"]
    assert len(bull) == 1
    f = bull[0]
    assert f["bottom"] == 1.00
    assert f["top"] == 1.01
    assert abs(f["ce"] - 1.005) < 1e-9


def test_fvg_not_detected_before_confirming_bar_exists():
    df = _bars([1.00, 1.02, 1.03], [0.99, 1.00, 1.01])
    # as_of at bar 1 timestamp: bar 2 has not yet occurred
    as_of = int(df.iloc[1]["ts_utc"])
    fvgs = detect_fvgs_at(df, as_of_ns=as_of)
    assert len([f for f in fvgs if f["kind"] == "bullish"]) == 0


def test_future_bar_mutation_does_not_change_past_fvg():
    df = _bars([1.00, 1.02, 1.03, 1.04, 1.05], [0.99, 1.00, 1.01, 1.03, 1.04])
    as_of = int(df.iloc[2]["ts_utc"]) + 1
    f1 = detect_fvgs_at(df, as_of_ns=as_of)
    df_mutated = df.copy()
    df_mutated.loc[df_mutated.index[3:], "bid_h"] = 999.0
    df_mutated.loc[df_mutated.index[3:], "bid_l"] = -999.0
    f2 = detect_fvgs_at(df_mutated, as_of_ns=as_of)
    assert f1 == f2


def test_bearish_fvg_detected():
    df = _bars([1.03, 1.02, 1.00], [1.02, 1.01, 0.99])
    as_of = int(df.iloc[2]["ts_utc"]) + 1
    fvgs = detect_fvgs_at(df, as_of_ns=as_of)
    bear = [f for f in fvgs if f["kind"] == "bearish"]
    assert len(bear) == 1
    # Bearish FVG: H_i=1.00, L_{i-2}=1.02 → range [1.00, 1.02]
    assert bear[0]["top"] == 1.02
    assert bear[0]["bottom"] == 1.00
