from __future__ import annotations

from decimal import Decimal
from typing import Literal

import pandas as pd

from v17.backtest.cost import (
    PIP_SCALE,
    PIP_VALUE_PER_LOT,
    apply_entry_slippage,
    half_spread,
)
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
    side: Side,
    sl: Decimal,
    tp: Decimal,
    bar: pd.Series | None = None,
    bar_open: Decimal | None = None,
    bar_high: Decimal | None = None,
    bar_low: Decimal | None = None,
) -> tuple[Literal["sl", "tp", "none"], Decimal | None]:
    if bar is not None:
        bar_open = Decimal(str(float(bar["open"])))
        bar_high = Decimal(str(float(bar["high"])))
        bar_low = Decimal(str(float(bar["low"])))
    elif bar_open is None or bar_high is None or bar_low is None:
        raise ValueError("Either bar or (bar_open, bar_high, bar_low) must be provided")

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
    symbol: Symbol | None = None,
) -> Decimal:
    if symbol is not None:
        scale = Decimal(str(PIP_SCALE.get(symbol, 10000)))
        pip_val = PIP_VALUE_PER_LOT.get(symbol, pip_value_per_lot)
    else:
        scale = _PIP_SCALE
        pip_val = pip_value_per_lot

    if side == Side.BUY:
        pips = (exit_price - entry) * scale
    else:
        pips = (entry - exit_price) * scale
    return pips * pip_val * size_lots
