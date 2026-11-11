"""Connors RSI(2) engine catalog (cycle 4, S3). FX-only."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class RSI2EngineConfig:
    engine_id: str
    symbol: str
    priority_order: int


RSI2_CATALOG: Final[list[RSI2EngineConfig]] = [
    RSI2EngineConfig("RSI2-EURUSD", "EURUSD", 1),
    RSI2EngineConfig("RSI2-GBPUSD", "GBPUSD", 2),
]
