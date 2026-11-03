from decimal import Decimal

import pandas as pd

from v17.backtest.fills import entry_fill, exit_fill_on_bar, pnl_usd
from v17.common.types import Side, Symbol


def _bar(o: float, h: float, lo: float, c: float) -> pd.Series:
    return pd.Series({"open": o, "high": h, "low": lo, "close": c})


def test_entry_buy_includes_spread_and_slip() -> None:
    # FTMO Normal EURUSD: half_spread = 0.00003, slip = 0.00003 → +0.00006
    px = entry_fill(Side.BUY, Decimal("1.1000"), Symbol("EURUSD"))
    assert px == Decimal("1.10006")


def test_entry_sell_mirror() -> None:
    px = entry_fill(Side.SELL, Decimal("1.1000"), Symbol("EURUSD"))
    assert px == Decimal("1.09994")


def test_exit_buy_sl_hits() -> None:
    bar = _bar(1.1000, 1.1010, 1.0990, 1.1005)
    kind, px = exit_fill_on_bar(Side.BUY, Decimal("1.0995"), Decimal("1.1030"), bar)
    assert kind == "sl" and px == Decimal("1.0995")


def test_exit_buy_sl_gap_down() -> None:
    bar = _bar(1.0980, 1.0990, 1.0975, 1.0982)
    kind, px = exit_fill_on_bar(Side.BUY, Decimal("1.0995"), Decimal("1.1030"), bar)
    assert kind == "sl" and px == Decimal("1.0980")


def test_exit_buy_tp_hits() -> None:
    bar = _bar(1.1000, 1.1050, 1.0995, 1.1045)
    kind, px = exit_fill_on_bar(Side.BUY, Decimal("1.0990"), Decimal("1.1030"), bar)
    assert kind == "tp" and px == Decimal("1.1030")


def test_exit_same_bar_sl_first() -> None:
    bar = _bar(1.1000, 1.1050, 1.0980, 1.1045)
    kind, _px = exit_fill_on_bar(Side.BUY, Decimal("1.0995"), Decimal("1.1030"), bar)
    assert kind == "sl"


def test_pnl_long_win() -> None:
    assert pnl_usd(Side.BUY, Decimal("1.1000"), Decimal("1.1050"), Decimal("0.1")) == Decimal("50.0")


def test_pnl_short_win() -> None:
    assert pnl_usd(Side.SELL, Decimal("1.1050"), Decimal("1.1000"), Decimal("0.1")) == Decimal("50.0")
