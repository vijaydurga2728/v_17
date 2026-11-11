"""Frozen ORB Reversal rulebook constants.

NEVER EDIT WITHOUT USER APPROVAL AND SPEC AMENDMENT. Changes mid-cycle
invalidate MCPT p-values.

Source spec: docs/superpowers/specs/2026-11-11-orb-reversal-indices-design.md
"""
from __future__ import annotations

from typing import Final

# Opening range window (NY local time, HH:MM).
OR_WINDOW_NY: Final[tuple[str, str]] = ("09:30", "10:00")
OR_DURATION_MIN: Final[int] = 30

# Session window — entries/management only within this bound (NY local).
SESSION_WINDOW_NY: Final[tuple[str, str]] = ("09:30", "11:30")

# Reversal confirmation: close-back-inside OR must occur within this many
# minutes after the initial breakout bar for a signal to arm.
REVERSAL_CONFIRM_MAX_MIN: Final[int] = 15

# ATR used for stop placement (M1 close-to-close over 14 bars).
ATR_PERIOD_M1: Final[int] = 14
SL_ATR_MULT: Final[float] = 0.5  # stop = breakout extreme ± 0.5 * ATR_14

# Initial reward target expressed in R-multiples.
TARGET_R: Final[float] = 0.5

# FTMO circuit breakers (ORB cycle — tighter than SB's 4% soft).
DAILY_LOSS_SOFT_STOP: Final[float] = 0.03
TOTAL_LOSS_HARD_FREEZE: Final[float] = 0.08

# Trade frequency discipline.
MAX_TRADES_PER_DAY_PER_INSTRUMENT: Final[int] = 1

# Cost model (SP500 entries retained as dead config for later re-enable).
COST_SLIPPAGE_PTS: Final[dict[str, float]] = {
    "USATECHIDXUSD": 0.5,
    "USA500IDXUSD": 0.25,
}
COMMISSION_PER_LOT: Final[dict[str, float]] = {
    "USATECHIDXUSD": 0.0,
    "USA500IDXUSD": 0.0,
}
