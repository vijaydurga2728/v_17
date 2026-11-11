"""Frozen Donchian Channel Breakout constants (cycle 4, S2).

Spec: docs/superpowers/specs/2026-11-11-ensemble-h1-cycle4-design.md § 3 S2.
Turtle rule 1 applied at H1.
"""
from __future__ import annotations

from typing import Final

ENTRY_CHANNEL_H1: Final[int] = 20    # breakout window
TRAIL_CHANNEL_H1: Final[int] = 10    # opposite-channel trailing-stop window
TARGET_R: Final[float] = 2.0         # fixed 2R target

COST_SLIPPAGE_PTS: Final[dict[str, float]] = {
    "USATECHIDXUSD": 0.5,
    "USA500IDXUSD": 0.25,
}
COST_SLIPPAGE_PIPS_FX: Final[float] = 0.5
