from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from v17.common.clock import FrozenClock
from v17.common.dtos import AccountState, Tick
from v17.common.types import Symbol
from v17.live.alerter import NullAlerter
from v17.live.runner import LiveRunner
from v17.mt5.fake import FakeMT5

_SYM = Symbol("EURUSD")
_SYM2 = Symbol("GBPUSD")
_NOW = datetime(2026, 1, 6, 7, 30, tzinfo=UTC)


def _account() -> AccountState:
    return AccountState(
        equity=Decimal("100000"), balance=Decimal("100000"),
        starting_equity=Decimal("100000"), peak_equity=Decimal("100000"),
        daily_realized_pnl=Decimal("0"), total_realized_pnl=Decimal("0"),
        best_day_pnl=Decimal("0"), open_positions=0, trading_days_count=0,
        is_locked_today=False, kill_active=False,
    )


class _StaticCalendar:
    def events(self, start: datetime, end: datetime) -> list:
        return []
    def is_blackout(self, symbol: Symbol, at: datetime, window_min: int = 5) -> bool:
        return False


def _make_runner(tmp_path: Path, symbols: list[Symbol]) -> LiveRunner:
    fake = FakeMT5()
    fake.connect()
    fake.set_tick(_SYM, Tick(symbol=_SYM, ts=_NOW, bid=Decimal("1.09990"), ask=Decimal("1.09998")))
    from v17.structure.engine import DefaultStructureEngine
    from v17.risk.engine import DefaultRiskEngine
    from v17.setups.silver_bullet import SilverBullet
    from v17.setups.judas_swing import JudasSwing
    return LiveRunner(
        gateway=fake,
        structure_engine=DefaultStructureEngine(_SYM),
        setup_engines=[SilverBullet(), JudasSwing()],
        risk_engine=DefaultRiskEngine(),
        calendar=_StaticCalendar(),
        alerter=NullAlerter(),
        state_root=tmp_path,
        symbols=symbols,
        clock=FrozenClock(_NOW),
        initial_account=_account(),
    )


class TestRunnerTickPoll:
    def test_tick_poll_calls_tick_step_for_each_symbol(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path, [_SYM, _SYM2])
        called: list[Symbol] = []
        def fake_tick_step(symbol: Symbol) -> None:
            called.append(symbol)
        runner._tick_step = fake_tick_step  # type: ignore[method-assign]
        runner._tick_poll()
        assert called == [_SYM, _SYM2]

    def test_tick_poll_single_symbol(self, tmp_path: Path) -> None:
        runner = _make_runner(tmp_path, [_SYM])
        called: list[Symbol] = []
        def fake_tick_step(symbol: Symbol) -> None:
            called.append(symbol)
        runner._tick_step = fake_tick_step  # type: ignore[method-assign]
        runner._tick_poll()
        assert called == [_SYM]
