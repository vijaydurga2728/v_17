"""Spec §9: Model A (FVG proximal edge) and Model B (same FVG + OTE 62-79% zone, D7)."""

from __future__ import annotations

from dataclasses import dataclass

from v17.smc_sb.fvg import FVG


@dataclass(frozen=True)
class Order:
    side: int
    limit: float
    stop: float  # D9: exactly the far FVG boundary, no buffer


def model_a(fvg: FVG, side: int) -> Order:
    return Order(side, fvg.proximal, fvg.far)


def ote_zone(
    side: int, sweep_extreme: float, impulse_extreme: float, lo: float, hi: float
) -> tuple[float, float]:
    """D7 retracement zone (lower, upper).

    Long: anchors sweep low L and highest high H reached by MSS confirmation; zone [H - hi*(H-L), H - lo*(H-L)].
    Short: anchors sweep high H and lowest low L; zone [L + lo*(H-L), L + hi*(H-L)].
    """
    if side == 1:
        h, l = impulse_extreme, sweep_extreme  # noqa: E741
        return h - hi * (h - l), h - lo * (h - l)
    h, l = sweep_extreme, impulse_extreme  # noqa: E741
    return l + lo * (h - l), l + hi * (h - l)


def model_b_ok(
    fvg: FVG, side: int, sweep_extreme: float, impulse_extreme: float, lo: float, hi: float
) -> tuple[bool, tuple[float, float]]:
    """The FVG proximal edge must lie inside the OTE zone (inclusive); entry stays at that edge."""
    z = ote_zone(side, sweep_extreme, impulse_extreme, lo, hi)
    return z[0] <= fvg.proximal <= z[1], z
