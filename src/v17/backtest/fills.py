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


# =============================================================================
# ORB cycle: float-based pending-STOP + market fill simulators (Task 7).
# =============================================================================
# These are independent of the Decimal-based legacy API above. They operate on
# M1 bars presented as a pandas DataFrame with integer `ts_ns` and float OHLC.
# Side is a string ("long"/"short") to avoid coupling to v17.common.types.Side.


def simulate_fill_stop(
    bars: pd.DataFrame,
    armed_idx: int,
    side: str,
    stop_price: float,
    sl: float,
    tp: float,
    time_cap_ns: int,
    slippage_pts: float,
) -> dict | None:
    """Simulate a pending STOP order armed at bar `armed_idx`.

    Short: trigger when any bar.high >= stop_price (trade fades up into stop).
    Long:  trigger when any bar.low  <= stop_price (trade fades down into stop).
    Entry price includes adverse slippage: +slippage_pts (short) / -slippage_pts
    inverted to adverse for long = +slippage_pts above stop for long, meaning
    the long enters HIGHER than stop by slippage. For a long STOP placed BELOW
    price (classic buy-stop above current), that's unusual; ORB-reversal long
    buy-stops at OR_low AFTER a breakdown + close-back-inside. Convention:
    adverse slippage always moves the entry against the trader.

    Returns None if the STOP never triggers before time_cap_ns.
    Returns dict with entry_price, entry_idx, exit_price, exit_idx, exit_reason
    when filled and resolved (TP, SL, TIME).
    """
    if armed_idx < 0 or armed_idx >= len(bars):
        return None

    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    ts_ns = bars["ts_ns"].to_numpy()
    armed_ts = ts_ns[armed_idx]

    entry_idx = None
    entry_price = None
    for i in range(armed_idx, len(bars)):
        if ts_ns[i] - armed_ts > time_cap_ns:
            return None
        if side == "short":
            if highs[i] >= stop_price:
                entry_idx = i
                entry_price = stop_price + slippage_pts
                break
        elif side == "long":
            if lows[i] <= stop_price:
                entry_idx = i
                entry_price = stop_price - slippage_pts
                break
        else:
            raise ValueError(f"side must be 'long' or 'short'; got {side!r}")

    if entry_idx is None:
        return None

    # Walk forward to resolve TP / SL / time cap.
    for j in range(entry_idx, len(bars)):
        if ts_ns[j] - armed_ts > time_cap_ns:
            return {
                "entry_price": entry_price,
                "entry_idx": entry_idx,
                "exit_price": bars["close"].iloc[j],
                "exit_idx": j,
                "exit_reason": "TIME",
            }
        if side == "short":
            if highs[j] >= sl:
                return {"entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": sl, "exit_idx": j, "exit_reason": "SL"}
            if lows[j] <= tp:
                return {"entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": tp, "exit_idx": j, "exit_reason": "TP"}
        else:  # long
            if lows[j] <= sl:
                return {"entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": sl, "exit_idx": j, "exit_reason": "SL"}
            if highs[j] >= tp:
                return {"entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": tp, "exit_idx": j, "exit_reason": "TP"}

    # Ran out of bars before TP/SL/TIME hit.
    return {
        "entry_price": entry_price,
        "entry_idx": entry_idx,
        "exit_price": bars["close"].iloc[-1],
        "exit_idx": len(bars) - 1,
        "exit_reason": "TIME",
    }


def simulate_fill_market(
    bars: pd.DataFrame,
    entry_idx: int,
    side: str,
    sl: float,
    tp: float,
    time_cap_ns: int,
    slippage_pts: float,
) -> dict:
    """Simulate a market order filled at bars.open[entry_idx], adverse slippage applied.

    `slippage_pts` has no default — callers MUST pass it explicitly so cost
    model misconfiguration cannot silently under-report costs.
    """
    if entry_idx < 0 or entry_idx >= len(bars):
        raise IndexError(f"entry_idx {entry_idx} out of range for bars len {len(bars)}")

    opens = bars["open"].to_numpy()
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    ts_ns = bars["ts_ns"].to_numpy()
    entry_ts = ts_ns[entry_idx]

    if side == "short":
        entry_price = opens[entry_idx] - slippage_pts
    elif side == "long":
        entry_price = opens[entry_idx] + slippage_pts
    else:
        raise ValueError(f"side must be 'long' or 'short'; got {side!r}")

    for j in range(entry_idx, len(bars)):
        if ts_ns[j] - entry_ts > time_cap_ns:
            return {
                "entry_price": entry_price, "entry_idx": entry_idx,
                "exit_price": bars["close"].iloc[j], "exit_idx": j, "exit_reason": "TIME",
            }
        if side == "short":
            if highs[j] >= sl:
                return {"entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": sl, "exit_idx": j, "exit_reason": "SL"}
            if lows[j] <= tp:
                return {"entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": tp, "exit_idx": j, "exit_reason": "TP"}
        else:
            if lows[j] <= sl:
                return {"entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": sl, "exit_idx": j, "exit_reason": "SL"}
            if highs[j] >= tp:
                return {"entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": tp, "exit_idx": j, "exit_reason": "TP"}

    return {
        "entry_price": entry_price, "entry_idx": entry_idx,
        "exit_price": bars["close"].iloc[-1], "exit_idx": len(bars) - 1, "exit_reason": "TIME",
    }
