from __future__ import annotations

from bisect import bisect_left
from datetime import datetime
from pathlib import Path

import httpx

from v17.common.dtos import CalendarEvent
from v17.common.types import Symbol
from v17.data.calendar.archive import load_archive_dir
from v17.data.calendar.blackout import AFFECTED


class FFCalendarProvider:
    def __init__(self, cache_dir: Path, http: httpx.Client | None = None) -> None:
        self.cache_dir = cache_dir
        self.http = http
        self._cache: list[CalendarEvent] | None = None
        self._index: dict[Symbol, list[float]] = {}

    def _all(self) -> list[CalendarEvent]:
        # Memoize on first call; archive dir is immutable within a backtest run.
        if self._cache is None:
            self._cache = load_archive_dir(self.cache_dir)
            for sym, aff in AFFECTED.items():
                ts = [
                    e.at.timestamp()
                    for e in self._cache
                    if e.impact == "high" and e.currency in aff
                ]
                ts.sort()
                self._index[sym] = ts
        return self._cache

    def events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        return [e for e in self._all() if start <= e.at <= end]

    def is_blackout(self, symbol: Symbol, at: datetime, window_min: int = 5) -> bool:
        self._all()
        ts_list = self._index.get(symbol)
        if not ts_list:
            return False
        t = at.timestamp()
        w = float(window_min * 60)
        idx = bisect_left(ts_list, t - w)
        return bool(idx < len(ts_list) and ts_list[idx] <= t + w)
