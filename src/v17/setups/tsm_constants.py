"""Frozen Time-Series Momentum constants (cycle 4, S1).

Spec: docs/superpowers/specs/2026-11-11-ensemble-h1-cycle4-design.md § 3 S1.
"""
from __future__ import annotations

from typing import Final

# Lookback window in H1 bars for the sign-of-return signal.
LOOKBACK_H1: Final[int] = 480   # ~20 trading days

# Non-overlapping hold period in H1 bars after each rebalance.
HOLD_H1: Final[int] = 120       # ~5 trading days

# Stop and target in R-multiples. SL distance = SL_ATR_MULT * ATR_14(H1).
ATR_PERIOD_H1: Final[int] = 14
SL_ATR_MULT: Final[float] = 2.0
TARGET_R: Final[float] = 3.0    # 3R opposite-direction stop-target

# Cost model (per spec § 5).
COST_SLIPPAGE_PTS: Final[dict[str, float]] = {
    "USATECHIDXUSD": 0.5,
    "USA500IDXUSD": 0.25,
}
COST_SLIPPAGE_PIPS_FX: Final[float] = 0.5    # pips, converted to price via pip_size
