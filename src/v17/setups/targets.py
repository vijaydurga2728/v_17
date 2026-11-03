from __future__ import annotations

from decimal import Decimal

from v17.backtest.cost import PIP_SCALE
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


def pip_distance(
    a: Decimal, b: Decimal, scale: int = 10000, symbol: str | None = None
) -> Decimal:
    # Symbol-aware scale when provided; falls back to the FX-major default.
    if symbol is not None:
        scale = PIP_SCALE.get(symbol, scale)
    return abs(a - b) * Decimal(scale)
