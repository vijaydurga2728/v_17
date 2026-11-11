"""Donchian channel breakout engine catalog (cycle 4, S2)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class DonchianEngineConfig:
    engine_id: str
    symbol: str
    priority_order: int


DONCHIAN_CATALOG: Final[list[DonchianEngineConfig]] = [
    DonchianEngineConfig("DON-EURUSD",        "EURUSD",        1),
    DonchianEngineConfig("DON-GBPUSD",        "GBPUSD",        2),
    DonchianEngineConfig("DON-USATECHIDXUSD", "USATECHIDXUSD", 3),
]
