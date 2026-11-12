"""Cycle 6 position sizing with per-pair pip semantics + 2-leg split."""
from __future__ import annotations

import math

from v17.setups.c6_constants import PAIR_META


def _round_down(x: float, step: float = 0.01) -> float:
    return math.floor(x / step) * step


def size_position(
    symbol: str,
    equity_sod: float,
    risk_pct: float,
    entry: float,
    initial_stop: float,
) -> tuple[float, float, int]:
    meta = PAIR_META[symbol]
    pip_size = meta["pip_size"]
    pip_value_fn = meta["pip_value_per_lot"]
    r_price = abs(entry - initial_stop)
    r_pips_f = r_price / pip_size
    r_pips = int(round(r_pips_f))
    if r_pips <= 0:
        return 0.0, 0.0, 0
    risk_dollars = equity_sod * risk_pct
    pip_value = pip_value_fn(entry)
    lots_total = risk_dollars / (r_pips * pip_value)
    lots_total = _round_down(lots_total, 0.01)
    lots_leg = _round_down(lots_total / 2.0, 0.01)
    if lots_leg < 0.01:
        return 0.0, 0.0, r_pips
    return lots_leg, lots_leg, r_pips
