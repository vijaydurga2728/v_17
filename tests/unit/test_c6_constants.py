from v17.common.types import SUPPORTED_SYMBOLS, Symbol
from v17.setups import c6_constants as C


def test_symbols_registered():
    assert Symbol("AUDUSD") in SUPPORTED_SYMBOLS
    assert Symbol("USDJPY") in SUPPORTED_SYMBOLS
    assert Symbol("USA500IDXUSD") in SUPPORTED_SYMBOLS


def test_constants_locked_values():
    assert C.SESSION_ANCHOR_HOUR_UTC == 8
    assert C.HARD_FLAT_HOUR_MIN_UTC == (19, 30)
    assert C.ENTRY_WINDOW_START_UTC_HM == (8, 5)
    assert C.ENTRY_WINDOW_END_UTC_HM == (19, 0)
    assert C.NY_OPEN_BLACKOUT_UTC_HM == ((13, 30, 0), (13, 34, 59))
    assert C.NEWS_BLACKOUT_MIN == 15
    assert C.WARMUP_SPX_BARS == 12
    assert C.TRAIL_EMA_PERIOD == 20
    assert C.TRAIL_BUFFER_ATR_MULT == 0.25
    assert C.ATR_PERIOD == 14
    assert C.ATR_FLOOR_MULT == 0.75
    assert C.RISK_PCT == 0.005
    assert C.PORTFOLIO_RISK_PCT == 0.0075
    assert C.SOFT_LOSS_PCT == -0.015
    assert C.HARD_LOSS_PCT == -0.025
    assert C.PROFIT_STOP_PCT == 0.020
    assert C.MAX_TRADES_PER_DAY == 8
    assert C.MAX_CONSEC_LOSSES == 3
    assert C.K_GRID == (0.2, 0.3, 0.4, 0.5)
    assert C.SLOPE_WINDOW_GRID == (8, 12, 16, 20)
    assert C.CONFIRM_BODY_GRID == (0.3, 0.4, 0.5)


def test_pair_meta_audusd():
    m = C.PAIR_META["AUDUSD"]
    assert m["pip_size"] == 0.0001
    assert m["pip_value_per_lot"](1.0) == 10.0  # fixed


def test_pair_meta_usdjpy_variable():
    m = C.PAIR_META["USDJPY"]
    assert m["pip_size"] == 0.01
    # USDJPY pip value in USD = 1000 / price
    assert abs(m["pip_value_per_lot"](150.0) - 1000 / 150.0) < 1e-9
    assert abs(m["pip_value_per_lot"](100.0) - 10.0) < 1e-9
