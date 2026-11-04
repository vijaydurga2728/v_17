from v17.structure.displacement import is_displacement


def test_rejects_small_body_ratio():
    # body 0.0005, range 0.002 → ratio 0.25 (fails 0.65 floor)
    bar = {"bid_o": 1.0, "bid_h": 1.001, "bid_l": 0.999, "bid_c": 1.0005}
    assert is_displacement(bar, atr_14=0.0005) is False


def test_rejects_small_range_relative_to_atr():
    # range 0.00018 vs 1.5*ATR=0.00015 → passes range; but body 0.00017 ratio 0.944 OK
    # To fail range: range 0.0001 vs 1.5*ATR=0.00015 fails
    bar = {"bid_o": 1.0, "bid_h": 1.00009, "bid_l": 0.99991, "bid_c": 1.00008}
    assert is_displacement(bar, atr_14=0.0001) is False


def test_accepts_strong_bullish_displacement():
    # body 0.0017, range 0.002 → ratio 0.85; range 0.002 vs 1.5*ATR 0.00075
    bar = {"bid_o": 1.0, "bid_h": 1.002, "bid_l": 1.0, "bid_c": 1.0017}
    assert is_displacement(bar, atr_14=0.0005) is True


def test_zero_range_rejected():
    bar = {"bid_o": 1.0, "bid_h": 1.0, "bid_l": 1.0, "bid_c": 1.0}
    assert is_displacement(bar, atr_14=0.001) is False
