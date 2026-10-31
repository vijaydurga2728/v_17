from __future__ import annotations

from decimal import Decimal
from typing import Literal

import pandas as pd

from v17.backtest.cost import apply_entry_slippage, half_spread
from v17.common.types import Side, Symbol

_PIP_SCALE = Decimal("10000")


def entry_fill(side: Side, next_bar_open: Decimal, symbol: Symbol) -> Decimal:
    base = (
        next_bar_open + half_spread(symbol)
        if side == Side.BUY
        else next_bar_open - half_spread(symbol)
    )
    return apply_entry_slippage(side, base, symbol)


def exit_fill_on_bar(
    side: Side, sl: Decimal, tp: Decimal, bar: pd.Series
) -> tuple[Literal["sl", "tp", "none"], Decimal | None]:
    bar_open = Decimal(str(float(bar["open"])))
    bar_high = Decimal(str(float(bar["high"])))
    bar_low = Decimal(str(float(bar["low"])))
    if side == Side.BUY:
        if bar_low <= sl:
            return "sl", min(bar_open, sl)
        if bar_high >= tp:
            return "tp", max(bar_open, tp)
    else:
        if bar_high >= sl:
            return "sl", max(bar_open, sl)
        if bar_low <= tp:
            return "tp", min(bar_open, tp)
    return "none", None


def pnl_usd(
    side: Side,
    entry: Decimal,
    exit_price: Decimal,
    size_lots: Decimal,
    pip_value_per_lot: Decimal = Decimal("10"),
) -> Decimal:
    if side == Side.BUY:
        pips = (exit_price - entry) * _PIP_SCALE
    else:
        pips = (entry - exit_price) * _PIP_SCALE
    return pips * pip_value_per_lot * size_lots
