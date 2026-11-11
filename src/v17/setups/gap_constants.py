"""Frozen overnight gap-fade constants (cycle 3, 2026-11-11).

Source spec: docs/superpowers/specs/2026-11-11-overnight-gap-fade-design.md
"""
from __future__ import annotations

from typing import Final

# Cash-session boundaries (NY local time).
SESSION_OPEN_NY: Final[tuple[int, int]] = (9, 30)   # 09:30
SESSION_CLOSE_NY: Final[tuple[int, int]] = (16, 0)  # 16:00

# Gap magnitude filter as fraction of prior close.
GAP_MIN_PCT: Final[float] = 0.0030   # 0.30%
GAP_MAX_PCT: Final[float] = 0.0200   # 2.00%

# Targets expressed in R where 1R = |gap|.
TARGET_R: Final[float] = 0.5   # 50% gap-close

# FTMO breakers (unchanged from ORB cycle).
DAILY_LOSS_SOFT_STOP: Final[float] = 0.03
TOTAL_LOSS_HARD_FREEZE: Final[float] = 0.08
