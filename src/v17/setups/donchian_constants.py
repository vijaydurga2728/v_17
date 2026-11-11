"""Frozen Donchian Channel Breakout constants.

Cycle 4B (2026-11-11, [P-HACK-ACKNOWLEDGED]): rewritten to D1 per Turtle rule 1.
See docs/superpowers/specs/2026-11-11-cycle4b-correction-prereg.md § 3 S2.
"""
from __future__ import annotations

from typing import Final

ENTRY_CHANNEL_D1: Final[int] = 20    # breakout window (Turtle system 1)
TRAIL_CHANNEL_D1: Final[int] = 10    # opposite-channel exit window (Turtle system 1)

# Initial stop sized from daily ATR_20 (Turtle 'N').
ATR_PERIOD_D1: Final[int] = 20
SL_ATR_MULT: Final[float] = 2.0      # Turtle '2N' stop

# No fixed take-profit — trend-following relies on trailing exit only.

COST_SLIPPAGE_PTS: Final[dict[str, float]] = {
    "USATECHIDXUSD": 0.5,
    "USA500IDXUSD": 0.25,
}
COST_SLIPPAGE_PIPS_FX: Final[float] = 0.5
