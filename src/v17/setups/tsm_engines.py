"""Time-Series Momentum engine catalog (cycle 4, S1).

Three instruments; one engine per instrument. Shared constants from tsm_constants.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class TSMEngineConfig:
    engine_id: str
    symbol: str
    priority_order: int


TSM_CATALOG: Final[list[TSMEngineConfig]] = [
    TSMEngineConfig(engine_id="TSM-EURUSD",        symbol="EURUSD",        priority_order=1),
    TSMEngineConfig(engine_id="TSM-GBPUSD",        symbol="GBPUSD",        priority_order=2),
    TSMEngineConfig(engine_id="TSM-USATECHIDXUSD", symbol="USATECHIDXUSD", priority_order=3),
]
