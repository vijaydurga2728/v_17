from __future__ import annotations

from decimal import Decimal

from v17.common.types import Side


def rr(entry: Decimal, sl: Decimal, tp: Decimal, side: Side) -> Decimal:
    if side == Side.BUY:
        risk = entry - sl
        reward = tp - entry
    else:
        risk = sl - entry
        reward = entry - tp
    if risk <= 0:
        return Decimal("0")
    return (reward / risk).quantize(Decimal("0.01"))


def passes_rr(rr_: Decimal, min_rr: Decimal = Decimal("1.5")) -> bool:
    return rr_ >= min_rr


def pip_distance(a: Decimal, b: Decimal, scale: int = 10000) -> Decimal:
    return abs(a - b) * Decimal(scale)
