"""Frozen Connors RSI(2) constants.

Cycle 4B (2026-11-11, [P-HACK-ACKNOWLEDGED]): rewritten to Connors D1 long-only
on equity-index proxy. See docs/superpowers/specs/2026-11-11-cycle4b-correction-prereg.md § 3 S3.
"""
from __future__ import annotations

from typing import Final

RSI_PERIOD_D1: Final[int] = 2
LONG_THRESHOLD: Final[float] = 10.0        # enter long when RSI(2) < 10
SMA_EXIT_PERIOD_D1: Final[int] = 5         # exit on close > SMA(5) per Connors
TIME_CAP_D1: Final[int] = 10               # safety cap (no stop in Connors spec)

COST_SLIPPAGE_PTS_USATECH: Final[float] = 0.5
