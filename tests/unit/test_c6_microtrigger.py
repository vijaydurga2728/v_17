import numpy as np
import pandas as pd

from v17.setups.c6_microtrigger import compute_micro_signals


def _mk_fx(n: int, oc_pairs):
    ts0 = pd.Timestamp("2020-01-02 08:00:00", tz="UTC").value
    opens = np.array([p[0] for p in oc_pairs])
    closes = np.array([p[1] for p in oc_pairs])
    highs = np.maximum(opens, closes) + 0.00005
    lows = np.minimum(opens, closes) - 0.00005
    ts = np.array([ts0 + i * 5 * 60_000_000_000 for i in range(n)], dtype="int64")
    return pd.DataFrame({
        "ts_utc": ts,
        "bid_o": opens, "bid_h": highs, "bid_l": lows, "bid_c": closes,
        "ask_o": opens + 0.00002, "ask_h": highs + 0.00002,
        "ask_l": lows + 0.00002, "ask_c": closes + 0.00002,
        "bid_volume": 1, "ask_volume": 1, "spread_mid": 0.00002,
    })


def test_no_confirm_before_warmup():
    df = _mk_fx(5, [(1.0, 1.0001)] * 5)
    out = compute_micro_signals(df, confirm_body_mult=0.4)
    assert (~out["confirm_long"]).all()
    assert (~out["confirm_short"]).all()


def test_long_confirm_after_pullback():
    # Rising series: VWAP sits just below price; last bar pulls back to VWAP
    # then confirms with a big green bar.
    bars = [(1.0, 1.0010)] * 20 + [(1.0010, 1.0004), (1.0004, 1.0020)]
    df = _mk_fx(len(bars), bars)
    out = compute_micro_signals(df, confirm_body_mult=0.1, atr_period=5)
    assert out.iloc[-1]["confirm_long"] == True


def test_short_confirm_mirror():
    bars = [(1.0010, 1.0)] * 20 + [(1.0, 1.0006), (1.0006, 0.9990)]
    df = _mk_fx(len(bars), bars)
    out = compute_micro_signals(df, confirm_body_mult=0.1, atr_period=5)
    assert out.iloc[-1]["confirm_short"] == True


def test_tiny_body_rejected():
    # Pullback to VWAP but confirm bar body is below threshold.
    bars = [(1.0, 1.0010)] * 20 + [(1.0010, 1.0005), (1.0005, 1.00055)]
    df = _mk_fx(len(bars), bars)
    out = compute_micro_signals(df, confirm_body_mult=5.0, atr_period=5)  # huge threshold
    assert out.iloc[-1]["confirm_long"] == False
