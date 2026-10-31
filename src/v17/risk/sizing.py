from __future__ import annotations

from decimal import ROUND_DOWN, Decimal


def compute_lots(
    equity: Decimal,
    per_trade_pct: Decimal,
    stop_distance_pips: Decimal,
    pip_value_per_lot: Decimal,
    lot_step: Decimal,
    min_lot: Decimal,
) -> Decimal:
    if equity <= 0 or stop_distance_pips <= 0:
        return Decimal("0")
    risk_amount = equity * per_trade_pct / Decimal("100")
    risk_per_lot = stop_distance_pips * pip_value_per_lot
    if risk_per_lot <= 0:
        return Decimal("0")
    raw = risk_amount / risk_per_lot
    floored = (raw / lot_step).to_integral_value(rounding=ROUND_DOWN) * lot_step
    if floored < min_lot:
        return Decimal("0")
    return floored.quantize(lot_step)
