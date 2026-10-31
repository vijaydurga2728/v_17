from decimal import Decimal

from v17.backtest.cost import (
    apply_entry_slippage,
    apply_exit_slippage,
    commission,
    half_spread,
)
from v17.common.types import Side, Symbol


def test_half_spread_eurusd() -> None:
    assert half_spread(Symbol("EURUSD")) == Decimal("0.00004")


def test_entry_slippage_buy_up() -> None:
    assert apply_entry_slippage(Side.BUY, Decimal("1.1000"), Symbol("EURUSD")) == Decimal("1.10003")


def test_entry_slippage_sell_down() -> None:
    assert apply_entry_slippage(Side.SELL, Decimal("1.1000"), Symbol("EURUSD")) == Decimal("1.09997")


def test_exit_slippage_mirror() -> None:
    assert apply_exit_slippage(Side.BUY, Decimal("1.1000"), Symbol("EURUSD")) == Decimal("1.09997")
    assert apply_exit_slippage(Side.SELL, Decimal("1.1000"), Symbol("EURUSD")) == Decimal("1.10003")


def test_commission_ftmo_normal_is_zero() -> None:
    # FTMO Normal account is spread-only; no per-lot commission.
    assert commission(Decimal("1.0"), Symbol("EURUSD")) == Decimal("0.0")
    assert commission(Decimal("1.0"), Symbol("GBPUSD")) == Decimal("0.0")
