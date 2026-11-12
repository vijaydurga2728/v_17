from v17.backtest.c6_sizing import size_position


def test_audusd_sizing():
    # Equity 10000, risk 0.5% -> $50 risk. Entry 0.6500 stop 0.6480 -> 20 pips.
    # lots_total = 50 / (20 * 10) = 0.25 -> each leg 0.12 (round down from 0.125).
    a, b, r_pips = size_position("AUDUSD", 10000.0, 0.005, 0.6500, 0.6480)
    assert r_pips == 20
    assert a == 0.12
    assert b == 0.12


def test_usdjpy_sizing_at_150():
    # Equity 10000, risk 0.5% = $50. Entry 150.00 stop 149.80 = 20 pips.
    # pip value = 1000/150 = 6.6666... per 1.0 lot
    # lots_total = 50 / (20 * 6.6666) = 0.375 -> each leg 0.18 (round down from 0.1875).
    a, b, r_pips = size_position("USDJPY", 10000.0, 0.005, 150.00, 149.80)
    assert r_pips == 20
    assert a == 0.18
    assert b == 0.18


def test_sub_min_size_skipped():
    # Tiny R: risk 50, pip value 10, R=200 pips -> lots_total=0.025 -> legs 0.01
    # Make R very large so legs go below 0.01.
    a, b, r_pips = size_position("AUDUSD", 10000.0, 0.005, 0.6500, 0.4500)
    # R=2000 pips. lots_total=50/(2000*10)=0.0025 -> each leg 0.00 after round-down.
    assert a == 0.0
    assert b == 0.0


def test_unknown_symbol_raises():
    import pytest
    with pytest.raises(KeyError):
        size_position("XAUUSD", 10000.0, 0.005, 2000.0, 1990.0)
