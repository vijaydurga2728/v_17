from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from v17.common.clock import FrozenClock
from v17.common.dtos import CalendarEvent, Tick
from v17.common.types import Symbol
from v17.live.kill_switch import write_kill
from v17.live.preflight import PreFlight
from v17.mt5.fake import FakeMT5


_SYM = Symbol("EURUSD")
_NOW = datetime(2026, 1, 6, 7, 30, tzinfo=UTC)
_CLOCK = FrozenClock(_NOW)


def _tick() -> Tick:
    return Tick(symbol=_SYM, ts=_NOW, bid=Decimal("1.09990"), ask=Decimal("1.09998"))


class _StaticCalendar:
    def events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        return []

    def is_blackout(self, symbol: Symbol, at: datetime, window_min: int = 5) -> bool:
        return False


class _BrokenCalendar:
    def events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        raise RuntimeError("calendar not loaded")

    def is_blackout(self, symbol: Symbol, at: datetime, window_min: int = 5) -> bool:
        return False


def _gate(state_root: Path) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "GATE_PASSED").touch()


class TestPreFlightAllPass:
    def test_all_checks_pass(self, tmp_path: Path) -> None:
        _gate(tmp_path)
        fake = FakeMT5()
        fake.connect()
        fake.set_tick(_SYM, _tick())
        pf = PreFlight(tmp_path, fake, _StaticCalendar(), _SYM, _CLOCK)
        result = pf.run()
        assert result.ok
        assert result.reasons == []


class TestPreFlightNoGate:
    def test_missing_gate_fails(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        fake.connect()
        fake.set_tick(_SYM, _tick())
        pf = PreFlight(tmp_path, fake, _StaticCalendar(), _SYM, _CLOCK)
        result = pf.run()
        assert not result.ok
        assert any("GATE_PASSED" in r for r in result.reasons)


class TestPreFlightKill:
    def test_kill_sentinel_fails(self, tmp_path: Path) -> None:
        _gate(tmp_path)
        write_kill(tmp_path)
        fake = FakeMT5()
        fake.connect()
        fake.set_tick(_SYM, _tick())
        pf = PreFlight(tmp_path, fake, _StaticCalendar(), _SYM, _CLOCK)
        result = pf.run()
        assert not result.ok
        assert any("KILL" in r for r in result.reasons)


class TestPreFlightNoTick:
    def test_no_tick_fails(self, tmp_path: Path) -> None:
        _gate(tmp_path)
        fake = FakeMT5()
        fake.connect()
        # no tick set
        pf = PreFlight(tmp_path, fake, _StaticCalendar(), _SYM, _CLOCK)
        result = pf.run()
        assert not result.ok
        assert any("tick" in r.lower() or "mt5" in r.lower() for r in result.reasons)


class TestPreFlightCalendar:
    def test_broken_calendar_fails(self, tmp_path: Path) -> None:
        _gate(tmp_path)
        fake = FakeMT5()
        fake.connect()
        fake.set_tick(_SYM, _tick())
        pf = PreFlight(tmp_path, fake, _BrokenCalendar(), _SYM, _CLOCK)
        result = pf.run()
        assert not result.ok
        assert any("calendar" in r.lower() for r in result.reasons)


class TestPreFlightMultipleFailures:
    def test_reports_all_failures(self, tmp_path: Path) -> None:
        # No gate, no tick
        fake = FakeMT5()
        fake.connect()
        pf = PreFlight(tmp_path, fake, _StaticCalendar(), _SYM, _CLOCK)
        result = pf.run()
        assert not result.ok
        assert len(result.reasons) >= 2
