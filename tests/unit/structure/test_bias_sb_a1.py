import pandas as pd
import numpy as np
from v17.structure.bias import compute_d1_bias


def _d1(prices: list[float]) -> pd.DataFrame:
    ts = pd.date_range("2024-01-01", periods=len(prices), freq="D", tz="UTC")
    return pd.DataFrame({
        "ts_utc": ts.astype("int64"),
        "bid_c": prices,
        "ask_c": [p + 0.00002 for p in prices],
    })


def test_bias_bullish_when_structure_up_and_above_ema20():
    # Create uptrend with reversals: starts at 1.00, trending to 1.10,
    # with small pullbacks to create local highs/lows for pivot detection.
    prices = [1.00, 1.01, 1.00, 1.02, 1.01, 1.03, 1.02, 1.04, 1.03, 1.05,
              1.04, 1.06, 1.05, 1.07, 1.06, 1.08, 1.07, 1.09, 1.08, 1.10,
              1.09, 1.11, 1.10, 1.12, 1.11]
    df = _d1(prices)
    as_of = int(df.iloc[-1]["ts_utc"]) + 86_400_000_000_000
    bias = compute_d1_bias(df, as_of_utc_ns=as_of)
    assert bias == "BULLISH"


def test_bias_bearish_when_structure_down_and_below_ema20():
    # Create downtrend with reversals: starts at 1.10, trending to 1.00,
    # with small bounces to create local highs/lows for pivot detection.
    prices = [1.10, 1.09, 1.10, 1.08, 1.09, 1.07, 1.08, 1.06, 1.07, 1.05,
              1.06, 1.04, 1.05, 1.03, 1.04, 1.02, 1.03, 1.01, 1.02, 1.00,
              1.01, 0.99, 1.00, 0.98, 0.99]
    df = _d1(prices)
    as_of = int(df.iloc[-1]["ts_utc"]) + 86_400_000_000_000
    bias = compute_d1_bias(df, as_of_utc_ns=as_of)
    assert bias == "BEARISH"


def test_bias_none_when_structure_chop():
    prices = [1.0, 1.01, 0.99, 1.02, 0.98] * 5
    df = _d1(prices)
    as_of = int(df.iloc[-1]["ts_utc"]) + 86_400_000_000_000
    bias = compute_d1_bias(df, as_of_utc_ns=as_of)
    assert bias == "NONE"


def test_causality_no_future_bars_used():
    prices = list(np.linspace(1.00, 1.10, 30))
    df = _d1(prices)
    as_of = int(df.iloc[20]["ts_utc"])
    bias_at_20 = compute_d1_bias(df, as_of_utc_ns=as_of)
    df_more = df.copy()
    df_more.iloc[21:, df_more.columns.get_loc("bid_c")] = 999.0
    df_more.iloc[21:, df_more.columns.get_loc("ask_c")] = 999.0
    bias_at_20_mutated = compute_d1_bias(df_more, as_of_utc_ns=as_of)
    assert bias_at_20 == bias_at_20_mutated
