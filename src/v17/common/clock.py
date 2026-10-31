from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def now(self) -> datetime: ...
    def now_in(self, tz: str) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def now_in(self, tz: str) -> datetime:
        return self.now().astimezone(ZoneInfo(tz))


class FrozenClock:
    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("FrozenClock requires tz-aware datetime")
        self._at = at.astimezone(UTC)

    def now(self) -> datetime:
        return self._at

    def now_in(self, tz: str) -> datetime:
        return self._at.astimezone(ZoneInfo(tz))
