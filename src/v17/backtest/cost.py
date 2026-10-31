from __future__ import annotations

from decimal import Decimal

from v17.common.types import Side, Symbol

_PIP = Decimal("0.0001")

COST_MODEL: dict[str, dict[str, Decimal]] = {
    # FTMO Normal account defaults: spread-only, no commission.
    # Spreads reflect public FTMO Normal typical session averages.
    "EURUSD": {
        "spread_pips": Decimal("0.8"),
        "slippage_pips_per_side": Decimal("0.3"),
        "commission_per_lot": Decimal("0.0"),
    },
    "GBPUSD": {
        "spread_pips": Decimal("1.2"),
        "slippage_pips_per_side": Decimal("0.3"),
        "commission_per_lot": Decimal("0.0"),
    },
}


def _cfg(symbol: Symbol) -> dict[str, Decimal]:
    return COST_MODEL[symbol]


def apply_entry_slippage(side: Side, price: Decimal, symbol: Symbol) -> Decimal:
    slip = _cfg(symbol)["slippage_pips_per_side"] * _PIP
    return price + slip if side == Side.BUY else price - slip


def apply_exit_slippage(side: Side, price: Decimal, symbol: Symbol) -> Decimal:
    slip = _cfg(symbol)["slippage_pips_per_side"] * _PIP
    return price - slip if side == Side.BUY else price + slip


def half_spread(symbol: Symbol) -> Decimal:
    return _cfg(symbol)["spread_pips"] * _PIP / Decimal("2")


def commission(size_lots: Decimal, symbol: Symbol) -> Decimal:
    return _cfg(symbol)["commission_per_lot"] * size_lots
