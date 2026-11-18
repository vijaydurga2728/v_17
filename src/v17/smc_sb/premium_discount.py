"""Spec §8 / R8: equilibrium of the last confirmed daily swing range; longs in discount, shorts in premium."""

from __future__ import annotations

import math

from v17.smc_sb.market_bias import Bias


def equilibrium(bias: Bias) -> float:
    """(latest confirmed daily swing high + latest confirmed daily swing low) / 2; NaN if unavailable."""
    if math.isnan(bias.last_high) or math.isnan(bias.last_low):
        return float("nan")
    return (bias.last_high + bias.last_low) / 2


def zone(price: float, eq: float) -> str:
    if math.isnan(eq):
        return "unknown"
    return "discount" if price < eq else "premium" if price > eq else "equilibrium"


def eligible(side: int, price: float, eq: float) -> bool:
    """Strict: long requires price < eq, short requires price > eq."""
    if math.isnan(eq):
        return False
    return price < eq if side == 1 else price > eq
