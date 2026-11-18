"""R17 R-unit definitions and the 1% FTMO-simulation position size (D16; simulation only)."""

from __future__ import annotations


def r_unit(entry: float, stop: float, slippage: float, commission: float) -> float:
    """1R per unit = |entry - stop| + stop slippage + round-trip commission."""
    return abs(entry - stop) + slippage + commission


def est_reward(entry: float, target: float, commission: float) -> float:
    return abs(target - entry) - commission


def realized_r(side: int, entry: float, exit_px: float, unit: float, commission: float) -> float:
    return ((exit_px - entry) * side - commission) / unit


def position_size(equity: float, risk_pct: float, unit_pts: float, value_per_point: float) -> float:
    """Units such that a full 1R loss costs risk_pct of equity (FTMO drawdown simulation only)."""
    if unit_pts <= 0 or value_per_point <= 0:
        raise ValueError("unit_pts and value_per_point must be positive")
    return equity * risk_pct / (unit_pts * value_per_point)
