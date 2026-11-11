"""Overnight gap-fade engine catalog (cycle 3)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class GapEngineConfig:
    engine_id: str
    symbol: str
    priority_order: int


GAP_CATALOG: Final[list[GapEngineConfig]] = [
    GapEngineConfig(engine_id="GAP-NAS100", symbol="USATECHIDXUSD", priority_order=1),
]
