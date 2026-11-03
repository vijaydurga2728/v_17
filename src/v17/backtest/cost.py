from __future__ import annotations

from decimal import Decimal

from v17.common.types import Side, Symbol

_PIP = Decimal("0.0001")

COST_MODEL: dict[str, dict[str, Decimal]] = {
    # FTMO Normal account spreads — user-provided from FTMO Normal dashboard.
    # Values are midpoint of published typical London/NY-session range.
    "EURUSD": {
        "spread_pips": Decimal("0.6"),   # range 0.2-0.9
        "slippage_pips_per_side": Decimal("0.3"),
        "commission_per_lot": Decimal("0.0"),
    },
    "GBPUSD": {
        "spread_pips": Decimal("1.2"),   # range 0.8-1.7
        "slippage_pips_per_side": Decimal("0.3"),
        "commission_per_lot": Decimal("0.0"),
    },
    "EURGBP": {
        "spread_pips": Decimal("1.2"),   # EUR cross, no direct FTMO quote; conservative
        "slippage_pips_per_side": Decimal("0.3"),
        "commission_per_lot": Decimal("0.0"),
    },
    "USDJPY": {
        "spread_pips": Decimal("1.2"),   # range 0.7-1.8
        "slippage_pips_per_side": Decimal("0.3"),
        "commission_per_lot": Decimal("0.0"),
    },
    "AUDUSD": {
        "spread_pips": Decimal("0.8"),   # range 0.5-1.1
        "slippage_pips_per_side": Decimal("0.3"),
        "commission_per_lot": Decimal("0.0"),
    },
    "USDCAD": {
        "spread_pips": Decimal("1.2"),   # range 0.8-1.7
        "slippage_pips_per_side": Decimal("0.3"),
        "commission_per_lot": Decimal("0.0"),
    },
    "USDCHF": {
        "spread_pips": Decimal("0.9"),   # range 0.6-1.2
        "slippage_pips_per_side": Decimal("0.3"),
        "commission_per_lot": Decimal("0.0"),
    },
    "NZDUSD": {
        "spread_pips": Decimal("1.0"),
        "slippage_pips_per_side": Decimal("0.3"),
        "commission_per_lot": Decimal("0.0"),
    },
    # Indices (points, not pips).
    "USATECHIDXUSD": {   # NAS100 range 1.0-1.8
        "spread_pips": Decimal("1.4"),
        "slippage_pips_per_side": Decimal("0.5"),
        "commission_per_lot": Decimal("0.0"),
    },
    "USA500IDXUSD": {    # US500 range 0.4-0.8
        "spread_pips": Decimal("0.6"),
        "slippage_pips_per_side": Decimal("0.3"),
        "commission_per_lot": Decimal("0.0"),
    },
    "USA30IDXUSD": {     # US30 range 1.5-2.5
        "spread_pips": Decimal("2.0"),
        "slippage_pips_per_side": Decimal("0.5"),
        "commission_per_lot": Decimal("0.0"),
    },
}


# Per-symbol zone tolerance in PIPS (pip_size units for the symbol).
# FX: ~10 pips = 10 price-points-at-0.0001. Indices need much wider
# because price-level is 10,000× larger and zones often sit 50-200 points
# from current price at killzone minutes.
ZONE_TOLERANCE_BY_SYMBOL: dict[str, Decimal] = {
    "EURUSD": Decimal("2.5"),
    "GBPUSD": Decimal("2.5"),
    "EURGBP": Decimal("2.5"),
    "AUDUSD": Decimal("2.5"),
    "USDCAD": Decimal("2.5"),
    "USDCHF": Decimal("2.5"),
    "NZDUSD": Decimal("2.5"),
    "USDJPY": Decimal("3"),
    "USATECHIDXUSD": Decimal("5"),    # NAS100 points
    "USA500IDXUSD": Decimal("2"),     # US500 points
    "USA30IDXUSD": Decimal("15"),     # US30 points
}


# Per-symbol minimum SL distance in PIPS.
# FX: 2 pips protects against noise. Indices scale ~100× in points.
MIN_PIP_SL_BY_SYMBOL: dict[str, Decimal] = {
    "EURUSD": Decimal("2"),
    "GBPUSD": Decimal("2"),
    "EURGBP": Decimal("2"),
    "AUDUSD": Decimal("2"),
    "USDCAD": Decimal("2"),
    "USDCHF": Decimal("2"),
    "NZDUSD": Decimal("2"),
    "USDJPY": Decimal("2"),
    "USATECHIDXUSD": Decimal("5"),    # NAS100 min 5 points
    "USA500IDXUSD": Decimal("1"),     # US500 min 1 point
    "USA30IDXUSD": Decimal("5"),      # US30 min 5 points
}


# Per-symbol TP fallback distance in PIPS (same unit as pip_size).
# FX majors use 22 pips (preserves GBP/USDJPY structural edge found in prior
# sessions). Indices use larger values matched to typical 15m zone heights
# so R:R passes 1.5 on average zone sizes.
TP_FALLBACK_PIPS_BY_SYMBOL: dict[str, Decimal] = {
    "EURUSD": Decimal("22"),
    "GBPUSD": Decimal("22"),
    "EURGBP": Decimal("14"),  # EUR cross ATR calibrated (typical ADR 35-45 pips)
    "AUDUSD": Decimal("22"),
    "USDCAD": Decimal("22"),
    "USDCHF": Decimal("22"),
    "NZDUSD": Decimal("22"),
    "USDJPY": Decimal("22"),  # JPY pips are 0.01 scale; 22 pips = 0.22 price units
    "USATECHIDXUSD": Decimal("70"),  # NAS100 points (calibrated for 2015-2017 NY Killzone)
    "USA500IDXUSD": Decimal("12"),   # US500 points
    "USA30IDXUSD": Decimal("80"),    # US30 points
}


# Pip scale per symbol. FX majors 10000. JPY pairs 100. Indices 1.
PIP_SCALE: dict[str, int] = {
    "EURUSD": 10000,
    "GBPUSD": 10000,
    "EURGBP": 10000,
    "AUDUSD": 10000,
    "USDCAD": 10000,
    "USDCHF": 10000,
    "NZDUSD": 10000,
    "USDJPY": 100,
    "USATECHIDXUSD": 1,  # NAS100
    "USA500IDXUSD": 1,   # SPX500
    "USA30IDXUSD": 1,    # DJ30
}


# Pip value per 1.0 lot per 1 pip movement, in USD.
# User-approved. Verify against FTMO contract specs before deployment.
def pip_size(symbol: str) -> Decimal:
    """One pip in price units for a given symbol.

    FX majors: 0.0001. JPY pairs: 0.01. Indices/commodities/crypto: 1.0.
    """
    scale = PIP_SCALE.get(symbol, 10000)
    return Decimal(1) / Decimal(scale)


PIP_VALUE_PER_LOT: dict[str, Decimal] = {
    "EURUSD": Decimal("10"),
    "GBPUSD": Decimal("10"),
    "EURGBP": Decimal("10"),
    "AUDUSD": Decimal("10"),
    "USDCAD": Decimal("10"),
    "USDCHF": Decimal("10"),
    "NZDUSD": Decimal("10"),
    "USDJPY": Decimal("10"),
    "USATECHIDXUSD": Decimal("1"),   # NAS100 FTMO CFD $1/point/lot
    "USA500IDXUSD": Decimal("1"),    # US500 FTMO CFD $1/point/lot (not ES futures sizing)
    "USA30IDXUSD": Decimal("1"),     # US30 FTMO CFD $1/point/lot
}


def _cfg(symbol: Symbol) -> dict[str, Decimal]:
    return COST_MODEL[symbol]


def apply_entry_slippage(side: Side, price: Decimal, symbol: Symbol) -> Decimal:
    slip = _cfg(symbol)["slippage_pips_per_side"] * pip_size(symbol)
    return price + slip if side == Side.BUY else price - slip


def apply_exit_slippage(side: Side, price: Decimal, symbol: Symbol) -> Decimal:
    slip = _cfg(symbol)["slippage_pips_per_side"] * pip_size(symbol)
    return price - slip if side == Side.BUY else price + slip


def half_spread(symbol: Symbol) -> Decimal:
    return _cfg(symbol)["spread_pips"] * pip_size(symbol) / Decimal("2")


def commission(size_lots: Decimal, symbol: Symbol) -> Decimal:
    return _cfg(symbol)["commission_per_lot"] * size_lots
