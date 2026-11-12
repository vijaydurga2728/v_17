"""Cycle 6 engine catalog — two FX pairs, SPX regime driver."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Final

from v17.setups.c6_constants import PAIR_META


@dataclass(frozen=True)
class C6EngineConfig:
    engine_id: str
    symbol: str
    pip_size: float
    pip_value_per_lot: Callable[[float], float]
    priority_order: int


C6_CATALOG: Final[tuple[C6EngineConfig, ...]] = (
    C6EngineConfig(
        engine_id="C6-AUDUSD",
        symbol="AUDUSD",
        pip_size=PAIR_META["AUDUSD"]["pip_size"],
        pip_value_per_lot=PAIR_META["AUDUSD"]["pip_value_per_lot"],
        priority_order=1,
    ),
    C6EngineConfig(
        engine_id="C6-USDJPY",
        symbol="USDJPY",
        pip_size=PAIR_META["USDJPY"]["pip_size"],
        pip_value_per_lot=PAIR_META["USDJPY"]["pip_value_per_lot"],
        priority_order=2,
    ),
)

REGIME_DRIVER_SYMBOL: Final[str] = "USA500IDXUSD"
