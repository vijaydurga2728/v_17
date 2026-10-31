from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx

from v17.common.dtos import CalendarEvent
from v17.common.types import Symbol
from v17.data.calendar.archive import load_archive_dir
from v17.data.calendar.blackout import is_blackout as _blackout


class FFCalendarProvider:
    def __init__(self, cache_dir: Path, http: httpx.Client | None = None) -> None:
        self.cache_dir = cache_dir
        self.http = http
        self._cache: list[CalendarEvent] | None = None

    def _all(self) -> list[CalendarEvent]:
        # Memoize on first call; archive dir is immutable within a backtest run.
        if self._cache is None:
            self._cache = load_archive_dir(self.cache_dir)
        return self._cache

    def events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        return [e for e in self._all() if start <= e.at <= end]

    def is_blackout(self, symbol: Symbol, at: datetime, window_min: int = 5) -> bool:
        return _blackout(self._all(), symbol, at, window_min)
