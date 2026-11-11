"""Connors RSI(2) engine catalog.

Cycle 4B (2026-11-11, [P-HACK-ACKNOWLEDGED]): narrowed to NAS100 only
(QQQ proxy per Connors). FX dropped — no equity-drift bias.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class RSI2EngineConfig:
    engine_id: str
    symbol: str
    priority_order: int


RSI2_CATALOG: Final[list[RSI2EngineConfig]] = [
    RSI2EngineConfig("RSI2-USATECHIDXUSD", "USATECHIDXUSD", 1),
]
