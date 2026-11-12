"""Frozen Cycle 6 constants (SPX-led intraday risk-on/off FX).

Spec: docs/superpowers/specs/2026-11-12-cycle6-spx-led-fx-design.md
"""
from __future__ import annotations

from typing import Callable, Final

SESSION_ANCHOR_HOUR_UTC: Final[int] = 8
HARD_FLAT_HOUR_MIN_UTC: Final[tuple[int, int]] = (19, 30)
ENTRY_WINDOW_START_UTC_HM: Final[tuple[int, int]] = (8, 5)
ENTRY_WINDOW_END_UTC_HM: Final[tuple[int, int]] = (19, 0)
NY_OPEN_BLACKOUT_UTC_HM: Final[tuple[tuple[int, int, int], tuple[int, int, int]]] = (
    (13, 30, 0),
    (13, 34, 59),
)
NEWS_BLACKOUT_MIN: Final[int] = 15
WARMUP_SPX_BARS: Final[int] = 12
TRAIL_EMA_PERIOD: Final[int] = 20
TRAIL_BUFFER_ATR_MULT: Final[float] = 0.25
ATR_PERIOD: Final[int] = 14
ATR_FLOOR_MULT: Final[float] = 0.75

RISK_PCT: Final[float] = 0.005
PORTFOLIO_RISK_PCT: Final[float] = 0.0075
SOFT_LOSS_PCT: Final[float] = -0.015
HARD_LOSS_PCT: Final[float] = -0.025
PROFIT_STOP_PCT: Final[float] = 0.020
MAX_TRADES_PER_DAY: Final[int] = 8
MAX_CONSEC_LOSSES: Final[int] = 3

K_GRID: Final[tuple[float, ...]] = (0.2, 0.3, 0.4, 0.5)
SLOPE_WINDOW_GRID: Final[tuple[int, ...]] = (8, 12, 16, 20)
CONFIRM_BODY_GRID: Final[tuple[float, ...]] = (0.3, 0.4, 0.5)


def _audusd_pip_value(_price: float) -> float:
    return 10.0


def _usdjpy_pip_value(price: float) -> float:
    return 1000.0 / price


PAIR_META: Final[dict[str, dict]] = {
    "AUDUSD": {
        "pip_size": 0.0001,
        "pip_value_per_lot": _audusd_pip_value,
        "currencies": ("AUD", "USD"),
    },
    "USDJPY": {
        "pip_size": 0.01,
        "pip_value_per_lot": _usdjpy_pip_value,
        "currencies": ("USD", "JPY"),
    },
}
