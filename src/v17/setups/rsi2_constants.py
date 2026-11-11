"""Frozen Connors RSI(2) mean-reversion constants (cycle 4, S3).

Spec: docs/superpowers/specs/2026-11-11-ensemble-h1-cycle4-design.md § 3 S3.
Symmetric variant. FX-only (EURUSD, GBPUSD).
"""
from __future__ import annotations

from typing import Final

RSI_PERIOD_H1: Final[int] = 2
LONG_THRESHOLD: Final[float] = 10.0     # enter long when RSI(2) < 10
SHORT_THRESHOLD: Final[float] = 90.0    # enter short when RSI(2) > 90
EXIT_MID: Final[float] = 50.0           # exit when RSI(2) crosses back through 50
TIME_CAP_H1: Final[int] = 5             # fallback exit after 5 H1 bars

ATR_PERIOD_H1: Final[int] = 14
SL_ATR_MULT: Final[float] = 2.0         # SL distance = 2 * ATR_14

COST_SLIPPAGE_PIPS_FX: Final[float] = 0.5
