from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Protocol

from v17.common.dtos import Bar, CalendarEvent, Tick
from v17.common.types import TF, Symbol


class BarProvider(Protocol):
    def bars(
        self, symbol: Symbol, tf: TF, start: datetime, end: datetime
    ) -> Iterable[Bar]: ...


class TickProvider(Protocol):
    def ticks(self, symbol: Symbol) -> Iterator[Tick]: ...


class CalendarProvider(Protocol):
    def events(self, start: datetime, end: datetime) -> list[CalendarEvent]: ...

    def is_blackout(self, symbol: Symbol, at: datetime, window_min: int = 5) -> bool: ...
