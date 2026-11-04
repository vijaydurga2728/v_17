"""SB-03 displacement validator (Audit 1: RESEARCH_HYPOTHESIS)."""
from __future__ import annotations

from v17.setups.sb_constants import (
    DISPLACEMENT_BODY_RATIO_MIN,
    DISPLACEMENT_RANGE_ATR_MULT,
)


def is_displacement(bar: dict, atr_14: float) -> bool:
    """Return True iff bar qualifies as displacement per SB-03.

    - Body-to-range ratio >= DISPLACEMENT_BODY_RATIO_MIN (0.65).
    - Range >= DISPLACEMENT_RANGE_ATR_MULT (1.5) * ATR_14.

    Rejects zero-range bars.
    """
    o = float(bar["bid_o"])
    h = float(bar["bid_h"])
    l = float(bar["bid_l"])
    c = float(bar["bid_c"])
    rng = h - l
    if rng <= 0.0:
        return False
    body = abs(c - o)
    body_ratio = body / rng
    if body_ratio < DISPLACEMENT_BODY_RATIO_MIN:
        return False
    if rng < DISPLACEMENT_RANGE_ATR_MULT * float(atr_14):
        return False
    return True
