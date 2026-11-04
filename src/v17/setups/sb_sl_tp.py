"""SB-04 / SB-05 SL/TP computation with JS-06 buffer discipline.

Audit 1 classification: JS-06 pattern applied to SB is SOURCE_INTERPRETATION;
SL distance caps and R:R gate are ENGINEERING_CONSTRAINT.
"""
from __future__ import annotations

from dataclasses import dataclass

from v17.common.instrument_spec import pip_size
from v17.setups.sb_constants import (
    MIN_R_MULTIPLE,
    SL_BUFFER_FX_MIN_PIPS,
    SL_BUFFER_FX_MAX_PIPS,
    SL_BUFFER_USATECH_MAX_PTS,
)


class SBRejectError(ValueError):
    pass


@dataclass(frozen=True)
class SLTP:
    sl: float
    tp: float
    r_multiple: float


_FX_SYMBOLS = {"EURUSD", "GBPUSD", "EURGBP", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "USDJPY"}
_INDEX_SYMBOLS = {"USATECHIDXUSD", "USA500IDXUSD", "USA30IDXUSD"}


def _buffer_bounds(symbol: str) -> tuple[float, float]:
    """Return (min_buffer, max_buffer) in price units for the symbol."""
    pip = pip_size(symbol)
    if symbol in _FX_SYMBOLS:
        return SL_BUFFER_FX_MIN_PIPS * pip, SL_BUFFER_FX_MAX_PIPS * pip
    if symbol in _INDEX_SYMBOLS:
        # Convention: "min 2 pts" matches FX "min 2 pips" shape.
        return 2.0, SL_BUFFER_USATECH_MAX_PTS
    # Default to FX treatment.
    return SL_BUFFER_FX_MIN_PIPS * pip, SL_BUFFER_FX_MAX_PIPS * pip


def compute_sl_tp(
    side: str,
    entry: float,
    sweep_extreme: float,
    opposing_target: float,
    symbol: str,
) -> SLTP:
    buf_min, buf_max = _buffer_bounds(symbol)

    if side == "LONG":
        raw_sl = sweep_extreme - buf_min
        distance = entry - raw_sl
        if distance > buf_max:
            raise SBRejectError(
                f"SL distance {distance:.6f} exceeds max {buf_max:.6f} for {symbol}"
            )
        if distance < buf_min:
            raw_sl = entry - buf_min
            distance = buf_min
        reward = opposing_target - entry
        if reward <= 0:
            raise SBRejectError(
                f"Target {opposing_target:.6f} is not above entry {entry:.6f} for LONG"
            )
        r = reward / distance
        if r < MIN_R_MULTIPLE:
            raise SBRejectError(f"R:R {r:.3f} < {MIN_R_MULTIPLE}")
        return SLTP(sl=raw_sl, tp=opposing_target, r_multiple=r)

    if side == "SHORT":
        raw_sl = sweep_extreme + buf_min
        distance = raw_sl - entry
        if distance > buf_max:
            raise SBRejectError(
                f"SL distance {distance:.6f} exceeds max {buf_max:.6f} for {symbol}"
            )
        if distance < buf_min:
            raw_sl = entry + buf_min
            distance = buf_min
        reward = entry - opposing_target
        if reward <= 0:
            raise SBRejectError(
                f"Target {opposing_target:.6f} is not above entry {entry:.6f} for SHORT"
            )
        r = reward / distance
        if r < MIN_R_MULTIPLE:
            raise SBRejectError(f"R:R {r:.3f} < {MIN_R_MULTIPLE}")
        return SLTP(sl=raw_sl, tp=opposing_target, r_multiple=r)

    raise SBRejectError(f"Unknown side {side!r}")
