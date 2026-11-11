"""ORB Reversal engine catalog.

Single-engine cycle 2026-11-11: NAS100 only. SP500 (ORB-SP500) dropped
because `USA500IDXUSD` bars are not present locally. Re-enable when
data lands.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class ORBEngineConfig:
    engine_id: str
    symbol: str
    or_window_ny: tuple[str, str]
    session_window_ny: tuple[str, str]
    priority_order: int


ORB_CATALOG: Final[list[ORBEngineConfig]] = [
    ORBEngineConfig(
        engine_id="ORB-NAS100",
        symbol="USATECHIDXUSD",
        or_window_ny=("09:30", "10:00"),
        session_window_ny=("09:30", "11:30"),
        priority_order=1,
    ),
]
