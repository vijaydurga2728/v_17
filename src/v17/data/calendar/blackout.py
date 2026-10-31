from __future__ import annotations

from datetime import datetime, timedelta

from v17.common.dtos import CalendarEvent
from v17.common.types import Symbol

AFFECTED: dict[Symbol, set[str]] = {
    Symbol("EURUSD"): {"USD", "EUR"},
    Symbol("GBPUSD"): {"USD", "GBP"},
}


def is_blackout(
    events: list[CalendarEvent], symbol: Symbol, at: datetime, window_min: int = 5
) -> bool:
    delta = timedelta(minutes=window_min)
    affected = AFFECTED.get(symbol, set())
    for e in events:
        if e.impact != "high":
            continue
        if e.currency not in affected:
            continue
        if abs((e.at - at).total_seconds()) <= delta.total_seconds():
            return True
    return False
