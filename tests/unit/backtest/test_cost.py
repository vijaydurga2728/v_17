from decimal import Decimal

from v17.backtest.cost import (
    apply_entry_slippage,
    apply_exit_slippage,
    commission,
    half_spread,
)
from v17.common.types import Side, Symbol


def test_half_spread_eurusd() -> None:
    # FTMO Normal EURUSD = 0.6 pips midpoint; half-spread = 0.3 pips = 0.00003.
    assert half_spread(Symbol("EURUSD")) == Decimal("0.00003")


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


def test_cost_scaling_usdjpy() -> None:
    # USDJPY spread 1.2 pips -> half-spread = 0.6 pips = 0.006 (pip_size = 0.01)
    assert half_spread(Symbol("USDJPY")) == Decimal("0.006")
    # Slippage 0.3 pips = 0.003
    assert apply_entry_slippage(Side.BUY, Decimal("150.00"), Symbol("USDJPY")) == Decimal("150.003")


def test_cost_scaling_indices_nas100() -> None:
    # USATECHIDXUSD spread 1.4 points -> half-spread = 0.7 points (pip_size = 1.0)
    assert half_spread(Symbol("USATECHIDXUSD")) == Decimal("0.7")
    # Slippage 0.5 points = 0.5
    assert apply_entry_slippage(Side.BUY, Decimal("18000.0"), Symbol("USATECHIDXUSD")) == Decimal("18000.5")
    assert apply_exit_slippage(Side.BUY, Decimal("18000.0"), Symbol("USATECHIDXUSD")) == Decimal("17999.5")
