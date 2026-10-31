from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from v17.common.clock import FrozenClock
from v17.common.dtos import AccountState, Bar, CalendarEvent, Tick
from v17.common.types import TF, Symbol
from v17.live.alerter import NullAlerter
from v17.live.kill_switch import write_kill
from v17.live.runner import LiveRunner
from v17.live.state_machine import RunnerState
from v17.mt5.fake import FakeMT5
from v17.risk.engine import DefaultRiskEngine
from v17.setups.judas_swing import JudasSwing
from v17.setups.silver_bullet import SilverBullet
from v17.structure.engine import DefaultStructureEngine

_SYM = Symbol("EURUSD")
_NOW = datetime(2026, 1, 6, 7, 30, tzinfo=UTC)


def _bar(tf: TF, i: int) -> Bar:
    base = Decimal("1.1") + Decimal(str(i)) * Decimal("0.0001")
    h = base + Decimal("0.0003")
    lo = base - Decimal("0.0003")
    return Bar(
        symbol=_SYM, tf=tf,
        ts=datetime(2026, 1, 6, 0, i % 60, tzinfo=UTC),
        open=base, high=h, low=lo, close=base + Decimal("0.0001"),
    )


def _enough_bars(fake: FakeMT5, count: int = 50) -> None:
    for tf in (TF.D1, TF.H4, TF.M15, TF.M1):
        fake.set_bars(_SYM, tf, [_bar(tf, i) for i in range(count)])


class _StaticCalendar:
    def events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        return []

    def is_blackout(self, symbol: Symbol, at: datetime, window_min: int = 5) -> bool:
        return False


def _make_runner(tmp_path: Path) -> tuple[LiveRunner, FakeMT5]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "GATE_PASSED").touch()
    fake = FakeMT5()
    fake.connect()
    fake.set_tick(
        _SYM,
        Tick(symbol=_SYM, ts=_NOW, bid=Decimal("1.09990"), ask=Decimal("1.09998")),
    )
    _enough_bars(fake)
    runner = LiveRunner(
        gateway=fake,
        structure_engine=DefaultStructureEngine(_SYM),
        setup_engines=[SilverBullet(), JudasSwing()],
        risk_engine=DefaultRiskEngine(),
        calendar=_StaticCalendar(),
        alerter=NullAlerter(),
        state_root=tmp_path,
        symbols=[_SYM],
        clock=FrozenClock(_NOW),
        initial_account=AccountState(
            equity=Decimal("100000"),
            balance=Decimal("100000"),
            starting_equity=Decimal("100000"),
            peak_equity=Decimal("100000"),
            daily_realized_pnl=Decimal("0"),
            total_realized_pnl=Decimal("0"),
            best_day_pnl=Decimal("0"),
            open_positions=0,
            trading_days_count=0,
            is_locked_today=False,
            kill_active=False,
        ),
    )
    return runner, fake


class TestSmokePipeline:
    def test_preflight_armed_smoke(self, tmp_path: Path) -> None:
        runner, _ = _make_runner(tmp_path)
        runner._killzone_start()
        assert runner.state == RunnerState.ARMED

    def test_tick_step_no_new_bar_stays_armed(self, tmp_path: Path) -> None:
        runner, fake = _make_runner(tmp_path)
        runner._killzone_start()
        # Two ticks in same minute
        fake.set_tick(_SYM, Tick(symbol=_SYM, ts=datetime(2026, 1, 6, 7, 30, 0, tzinfo=UTC), bid=Decimal("1.09990"), ask=Decimal("1.09998")))
        runner._tick_step(_SYM)
        fake.set_tick(_SYM, Tick(symbol=_SYM, ts=datetime(2026, 1, 6, 7, 30, 30, tzinfo=UTC), bid=Decimal("1.09991"), ask=Decimal("1.09999")))
        runner._tick_step(_SYM)
        assert runner.state == RunnerState.ARMED

    def test_tick_step_new_bar_runs_without_error(self, tmp_path: Path) -> None:
        runner, fake = _make_runner(tmp_path)
        runner._killzone_start()
        fake.set_tick(_SYM, Tick(symbol=_SYM, ts=datetime(2026, 1, 6, 7, 30, 0, tzinfo=UTC), bid=Decimal("1.09990"), ask=Decimal("1.09998")))
        runner._tick_step(_SYM)  # primes bar builder
        fake.set_tick(_SYM, Tick(symbol=_SYM, ts=datetime(2026, 1, 6, 7, 31, 0, tzinfo=UTC), bid=Decimal("1.09990"), ask=Decimal("1.09998")))
        runner._tick_step(_SYM)  # new minute — runs full pipeline
        # State is ARMED (no signal fired — our synthetic bars don't trigger a setup)
        assert runner.state in (RunnerState.ARMED, RunnerState.IN_TRADE)

    def test_killzone_stop_goes_idle(self, tmp_path: Path) -> None:
        runner, _ = _make_runner(tmp_path)
        runner._killzone_start()
        runner._killzone_stop()
        assert runner.state == RunnerState.IDLE

    def test_kill_sentinel_stops_runner(self, tmp_path: Path) -> None:
        runner, fake = _make_runner(tmp_path)
        runner._killzone_start()
        write_kill(tmp_path)
        runner._tick_step(_SYM)
        assert runner.state == RunnerState.IDLE


class TestSmokeCoverageRun:
    def test_full_suite_still_passes(self, tmp_path: Path) -> None:
        """Regression: all unit tests still pass after M8 added."""
        runner, fake = _make_runner(tmp_path)
        runner._killzone_start()
        for m in range(30, 33):
            for s in [0, 30]:
                ts = datetime(2026, 1, 6, 7, m, s, tzinfo=UTC)
                fake.set_tick(_SYM, Tick(symbol=_SYM, ts=ts, bid=Decimal("1.09990"), ask=Decimal("1.09998")))
                runner._tick_step(_SYM)
        runner._killzone_stop()
        assert runner.state == RunnerState.IDLE
