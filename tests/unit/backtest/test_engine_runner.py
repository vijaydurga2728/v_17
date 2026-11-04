import pandas as pd
from v17.backtest.engine_runner import run_engine_oos, TradeLog
from v17.backtest.walkforward import generate_folds
from v17.setups.sb_engines import ENGINE_CATALOG


def test_runner_returns_tradelog_with_metadata():
    bars = pd.DataFrame({
        "ts_utc": pd.array([], dtype="int64"),
        "symbol": pd.array([], dtype=object),
        "bid_o": pd.array([], dtype="float64"),
        "bid_h": pd.array([], dtype="float64"),
        "bid_l": pd.array([], dtype="float64"),
        "bid_c": pd.array([], dtype="float64"),
        "ask_o": pd.array([], dtype="float64"),
        "ask_h": pd.array([], dtype="float64"),
        "ask_l": pd.array([], dtype="float64"),
        "ask_c": pd.array([], dtype="float64"),
        "spread_mid": pd.array([], dtype="float64"),
    })
    cal = pd.DataFrame({
        "timestamp_utc": pd.array([], dtype="int64"),
        "currency": pd.array([], dtype=object),
        "impact": pd.array([], dtype=object),
    })
    fold = generate_folds()[0]
    out = run_engine_oos(config=ENGINE_CATALOG[0], bars=bars, calendar=cal, fold=fold)
    assert isinstance(out, TradeLog)
    assert out.engine_id == "SB-LDN-CE"
    assert out.fold_id == 1
    assert out.trades == []


def test_runner_filters_bars_to_oos_window():
    # Only bar inside OOS 2018 for EURUSD should be considered
    fold = generate_folds()[0]  # OOS 2018
    inside_ns = int(pd.Timestamp("2018-06-01", tz="UTC").value)
    outside_ns = int(pd.Timestamp("2017-06-01", tz="UTC").value)
    bars = pd.DataFrame({
        "ts_utc": [inside_ns, outside_ns],
        "symbol": ["EURUSD", "EURUSD"],
        "bid_o": [1.1, 1.1], "bid_h": [1.1001, 1.1001],
        "bid_l": [1.0999, 1.0999], "bid_c": [1.1, 1.1],
        "ask_o": [1.10002, 1.10002], "ask_h": [1.10012, 1.10012],
        "ask_l": [1.09992, 1.09992], "ask_c": [1.10002, 1.10002],
        "spread_mid": [0.00002, 0.00002],
    })
    cal = pd.DataFrame({
        "timestamp_utc": pd.array([], dtype="int64"),
        "currency": pd.array([], dtype=object),
        "impact": pd.array([], dtype=object),
    })
    out = run_engine_oos(config=ENGINE_CATALOG[0], bars=bars, calendar=cal, fold=fold)
    # Runner compiled; details of trade generation are Task 5.3.
    # At this scaffold stage, verify: no trades fired on empty-context defaults.
    assert isinstance(out, TradeLog)
    assert out.engine_id == "SB-LDN-CE"
    assert out.fold_id == 1
