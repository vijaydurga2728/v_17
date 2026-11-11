"""Frozen Time-Series Momentum constants.

Cycle 4B (2026-11-11, [P-HACK-ACKNOWLEDGED]): rewritten to D1 per Moskowitz
paper time-series arm. See docs/superpowers/specs/2026-11-11-cycle4b-correction-prereg.md.
"""
from __future__ import annotations

from typing import Final

# Lookback in D1 bars for sign-of-return signal (~12 months per paper).
LOOKBACK_D1: Final[int] = 252

# Non-overlapping hold period in D1 bars (~1 month per paper).
HOLD_D1: Final[int] = 21

# Stop sized from daily ATR. No hard target — exit on hold-period end or SL.
ATR_PERIOD_D1: Final[int] = 14
SL_ATR_MULT: Final[float] = 2.0

# Cost model carries over from cycle-4 (indices + FX majors).
COST_SLIPPAGE_PTS: Final[dict[str, float]] = {
    "USATECHIDXUSD": 0.5,
    "USA500IDXUSD": 0.25,
}
COST_SLIPPAGE_PIPS_FX: Final[float] = 0.5
