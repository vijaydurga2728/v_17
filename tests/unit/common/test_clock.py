from datetime import UTC, datetime

from v17.common.clock import Clock, FrozenClock, SystemClock


def test_system_clock_utc() -> None:
    c = SystemClock()
    assert c.now().tzinfo is UTC


def test_frozen_clock() -> None:
    t = datetime(2026, 10, 28, 7, 30, tzinfo=UTC)
    c: Clock = FrozenClock(t)
    assert c.now() == t


def test_now_in_zone() -> None:
    t = datetime(2026, 10, 28, 7, 30, tzinfo=UTC)
    c = FrozenClock(t)
    assert c.now_in("Europe/London").hour in {7, 8}
