from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from v17.common.clock import FrozenClock
from v17.common.dtos import AccountState, Bar, CalendarEvent, OrderRequest, OrderResult, Position, Tick
from v17.common.errors import V17StructureError
from v17.common.types import TF, Side, Symbol, Ticket
from v17.live.alerter import NullAlerter
from v17.live.kill_switch import write_kill
from v17.live.runner import LiveRunner
from v17.live.state_machine import RunnerState
from v17.mt5.fake import FakeMT5
from v17.structure.engine import DefaultStructureEngine


_SYM = Symbol("EURUSD")
_NOW = datetime(2026, 1, 6, 7, 30, tzinfo=UTC)


def _tick(m: int = 30, s: int = 0) -> Tick:
    return Tick(
        symbol=_SYM,
        ts=datetime(2026, 1, 6, 7, m, s, tzinfo=UTC),
        bid=Decimal("1.09990"),
        ask=Decimal("1.09998"),
    )


def _account() -> AccountState:
    return AccountState(
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
    )


class _StaticCalendar:
    def events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        return []

    def is_blackout(self, symbol: Symbol, at: datetime, window_min: int = 5) -> bool:
        return False


def _make_runner(
    tmp_path: Path,
    fake: FakeMT5,
    with_gate: bool = True,
    symbols: list[Symbol] | None = None,
) -> LiveRunner:
    syms = symbols or [_SYM]
    if with_gate:
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "GATE_PASSED").touch()
    fake.connect()
    for s in syms:
        fake.set_tick(s, _tick())
    clock = FrozenClock(_NOW)
    structure = DefaultStructureEngine(syms[0])
    from v17.risk.engine import DefaultRiskEngine
    from v17.setups.silver_bullet import SilverBullet
    from v17.setups.judas_swing import JudasSwing
    return LiveRunner(
        gateway=fake,
        structure_engine=structure,
        setup_engines=[SilverBullet(), JudasSwing()],
        risk_engine=DefaultRiskEngine(),
        calendar=_StaticCalendar(),
        alerter=NullAlerter(),
        state_root=tmp_path,
        symbols=syms,
        clock=clock,
        initial_account=_account(),
    )


class TestRunnerPreFlight:
    def test_killzone_start_sets_armed_when_gate_present(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake)
        runner._killzone_start()
        assert runner.state == RunnerState.ARMED

    def test_killzone_start_stays_idle_when_no_gate(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake, with_gate=False)
        runner._killzone_start()
        assert runner.state == RunnerState.IDLE

    def test_killzone_stop_sets_idle(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake)
        runner._killzone_start()
        assert runner.state == RunnerState.ARMED
        runner._killzone_stop()
        assert runner.state == RunnerState.IDLE


class TestRunnerKillSwitch:
    def test_kill_sentinel_transitions_to_idle(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake)
        runner._killzone_start()
        assert runner.state == RunnerState.ARMED
        write_kill(tmp_path)
        # tick_step detects KILL
        runner._tick_step(_SYM)
        assert runner.state == RunnerState.IDLE


class TestRunnerReconcile:
    def test_reconcile_open_position_sets_in_trade(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake)
        runner._killzone_start()
        assert runner.state == RunnerState.ARMED
        fake._positions[1] = Position(
            ticket=Ticket(1),
            symbol=_SYM,
            side=Side.BUY,
            size_lots=Decimal("0.01"),
            opened_at=_NOW,
            entry=Decimal("1.09998"),
            sl=Decimal("1.09800"),
            tp=Decimal("1.10200"),
            current_price=Decimal("1.09998"),
            unrealized_pnl=Decimal("0"),
        )
        runner._reconcile()
        assert runner.state == RunnerState.IN_TRADE

    def test_reconcile_no_positions_stays_armed(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake)
        runner._killzone_start()
        runner._reconcile()
        assert runner.state == RunnerState.ARMED

    def test_reconcile_multiple_symbols_restores_all(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake, symbols=[Symbol("EURUSD"), Symbol("GBPUSD")])
        runner._killzone_start()
        fake._positions[1] = Position(
            ticket=Ticket(1),
            symbol=Symbol("EURUSD"),
            side=Side.BUY,
            size_lots=Decimal("0.01"),
            opened_at=_NOW,
            entry=Decimal("1.09998"),
            sl=Decimal("1.09800"),
            tp=Decimal("1.10200"),
            current_price=Decimal("1.09998"),
            unrealized_pnl=Decimal("0"),
        )
        fake._positions[2] = Position(
            ticket=Ticket(2),
            symbol=Symbol("GBPUSD"),
            side=Side.SELL,
            size_lots=Decimal("0.02"),
            opened_at=_NOW,
            entry=Decimal("1.25000"),
            sl=Decimal("1.25500"),
            tp=Decimal("1.24000"),
            current_price=Decimal("1.25000"),
            unrealized_pnl=Decimal("0"),
        )
        runner._reconcile()
        assert runner.state == RunnerState.IN_TRADE
        assert len(runner.open_trades) == 2
        assert Symbol("EURUSD") in runner.open_trades
        assert Symbol("GBPUSD") in runner.open_trades


class TestRunnerTickStep:
    def test_tick_step_armed_no_new_bar_stays_armed(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake)
        runner._killzone_start()
        # Two ticks in same minute — no new bar
        fake.set_tick(_SYM, _tick(30, 0))
        runner._tick_step(_SYM)  # primes bar builder
        fake.set_tick(_SYM, _tick(30, 30))
        runner._tick_step(_SYM)  # same minute
        assert runner.state == RunnerState.ARMED


class TestRunnerStop:
    def test_stop_sets_idle(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake)
        runner._killzone_start()
        assert runner.state == RunnerState.ARMED
        runner.stop()
        assert runner.state == RunnerState.IDLE


class TestRunnerTickStepNoneTick:
    def test_none_tick_returns_without_state_change(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake)
        runner._killzone_start()
        assert runner.state == RunnerState.ARMED
        fake._ticks.clear()
        runner._tick_step(_SYM)
        assert runner.state == RunnerState.ARMED


class TestRunnerBlackout:
    def test_blackout_skips_processing(self, tmp_path: Path) -> None:
        class BlackoutCalendar:
            def events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
                return []

            def is_blackout(self, symbol: Symbol, at: datetime, window_min: int = 5) -> bool:
                return True

        fake = FakeMT5()
        fake.connect()
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "GATE_PASSED").touch()
        fake.set_tick(_SYM, _tick())
        clock = FrozenClock(_NOW)
        structure = DefaultStructureEngine(_SYM)
        from v17.risk.engine import DefaultRiskEngine
        from v17.setups.silver_bullet import SilverBullet
        from v17.setups.judas_swing import JudasSwing
        runner = LiveRunner(
            gateway=fake,
            structure_engine=structure,
            setup_engines=[SilverBullet(), JudasSwing()],
            risk_engine=DefaultRiskEngine(),
            calendar=BlackoutCalendar(),
            alerter=NullAlerter(),
            state_root=tmp_path,
            symbols=[_SYM],
            clock=clock,
            initial_account=_account(),
        )
        runner._killzone_start()
        assert runner.state == RunnerState.ARMED
        runner._tick_step(_SYM)
        assert runner.state == RunnerState.ARMED


class TestRunnerStructureError:
    def test_structure_error_is_caught(self, tmp_path: Path) -> None:
        class FailingStructure:
            def analyze(self, bars_by_tf: object) -> object:
                raise V17StructureError("test error")

        fake = FakeMT5()
        fake.connect()
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "GATE_PASSED").touch()
        fake.set_tick(_SYM, _tick())
        base = Decimal("1.1")
        for tf in (TF.D1, TF.H4, TF.M15, TF.M1):
            bars = [
                Bar(
                    symbol=_SYM,
                    tf=tf,
                    ts=datetime(2026, 1, 6, 0, i % 60, tzinfo=UTC),
                    open=base + Decimal(str(i)) * Decimal("0.0001"),
                    high=base + Decimal(str(i)) * Decimal("0.0001") + Decimal("0.0003"),
                    low=base + Decimal(str(i)) * Decimal("0.0001") - Decimal("0.0003"),
                    close=base + Decimal(str(i)) * Decimal("0.0001") + Decimal("0.0001"),
                )
                for i in range(25)
            ]
            fake.set_bars(_SYM, tf, bars)
        clock = FrozenClock(_NOW)
        from v17.risk.engine import DefaultRiskEngine
        from v17.setups.silver_bullet import SilverBullet
        from v17.setups.judas_swing import JudasSwing
        runner = LiveRunner(
            gateway=fake,
            structure_engine=FailingStructure(),  # type: ignore[arg-type]
            setup_engines=[SilverBullet(), JudasSwing()],
            risk_engine=DefaultRiskEngine(),
            calendar=_StaticCalendar(),
            alerter=NullAlerter(),
            state_root=tmp_path,
            symbols=[_SYM],
            clock=clock,
            initial_account=_account(),
        )
        runner._killzone_start()
        assert runner.state == RunnerState.ARMED
        fake.set_tick(
            _SYM,
            Tick(
                symbol=_SYM,
                ts=datetime(2026, 1, 6, 7, 30, 0, tzinfo=UTC),
                bid=Decimal("1.09990"),
                ask=Decimal("1.09998"),
            ),
        )
        runner._tick_step(_SYM)
        fake.set_tick(
            _SYM,
            Tick(
                symbol=_SYM,
                ts=datetime(2026, 1, 6, 7, 31, 0, tzinfo=UTC),
                bid=Decimal("1.09990"),
                ask=Decimal("1.09998"),
            ),
        )
        runner._tick_step(_SYM)
        assert runner.state == RunnerState.ARMED


class TestRunnerProcessInTrade:
    def test_position_disappears_transitions_to_armed(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake)
        runner._killzone_start()
        assert runner.state == RunnerState.ARMED

        fake._positions[1] = Position(
            ticket=Ticket(1),
            symbol=_SYM,
            side=Side.BUY,
            size_lots=Decimal("0.01"),
            opened_at=_NOW,
            entry=Decimal("1.09998"),
            sl=Decimal("1.09800"),
            tp=Decimal("1.10200"),
            current_price=Decimal("1.09998"),
            unrealized_pnl=Decimal("0"),
        )
        runner._reconcile()
        assert runner.state == RunnerState.IN_TRADE
        assert runner._open_trade is not None

        del fake._positions[1]

        fake.set_tick(
            _SYM,
            Tick(
                symbol=_SYM,
                ts=datetime(2026, 1, 6, 7, 31, 0, tzinfo=UTC),
                bid=Decimal("1.09990"),
                ask=Decimal("1.09998"),
            ),
        )
        runner._tick_step(_SYM)
        assert runner.state == RunnerState.ARMED
        assert runner._open_trade is None

    def test_position_still_open_stays_in_trade(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake)
        runner._killzone_start()

        fake._positions[1] = Position(
            ticket=Ticket(1),
            symbol=_SYM,
            side=Side.BUY,
            size_lots=Decimal("0.01"),
            opened_at=_NOW,
            entry=Decimal("1.09998"),
            sl=Decimal("1.09800"),
            tp=Decimal("1.10200"),
            current_price=Decimal("1.09998"),
            unrealized_pnl=Decimal("0"),
        )
        runner._reconcile()
        assert runner.state == RunnerState.IN_TRADE

        runner._tick_step(_SYM)
        assert runner.state == RunnerState.IN_TRADE


class TestRunnerPostFillRiskCheck:
    def test_post_fill_breach_triggers_emergency_close(self, tmp_path: Path) -> None:
        fake = FakeMT5()
        runner = _make_runner(tmp_path, fake)
        runner._killzone_start()

        class SlippingFakeMT5(FakeMT5):
            def order_send(self, order: OrderRequest) -> OrderResult:
                # Fills at an extreme slippage price that breaches risk (e.g. at/below SL for BUY)
                t = self._ticks[str(order.symbol)]
                ticket = Ticket(self._next_ticket)
                self._next_ticket += 1
                bad_fill = order.sl - Decimal("0.0010")  # below SL!
                pos = Position(
                    ticket=ticket,
                    symbol=order.symbol,
                    side=order.side,
                    size_lots=order.size_lots,
                    opened_at=t.ts,
                    entry=bad_fill,
                    sl=order.sl,
                    tp=order.tp,
                    current_price=bad_fill,
                    unrealized_pnl=Decimal("0"),
                )
                self._positions[int(ticket)] = pos
                return OrderResult(ok=True, ticket=ticket, filled_price=bad_fill, filled_at=t.ts)

        slipping_fake = SlippingFakeMT5()
        slipping_runner = _make_runner(tmp_path, slipping_fake)
        slipping_runner._killzone_start()

        # Mock setup engine returning a BUY signal
        from v17.common.dtos import Signal
        from v17.common.types import SignalId
        sig = Signal(
            id=SignalId("test_sig"),
            symbol=_SYM,
            setup="silver_bullet",
            side=Side.BUY,
            at=_NOW,
            entry=Decimal("1.1000"),
            sl=Decimal("1.0980"),
            tp=Decimal("1.1040"),
            rr=Decimal("2.0"),
            confluence={"bias": True, "fvg": True, "ob": True, "mss": True, "sweep": True},
        )
        class DummySetup:
            def evaluate(self, snap: object, ts: object, bars_1m: object) -> Signal | None:
                return sig

        slipping_runner._setup_engines = [DummySetup()]  # type: ignore[list-item]

        # Feed a tick with a new bar to trigger armed processing
        base = Decimal("1.1")
        for tf in (TF.D1, TF.H4, TF.M15, TF.M1):
            bars = [
                Bar(
                    symbol=_SYM,
                    tf=tf,
                    ts=datetime(2026, 1, 6, 0, i % 60, tzinfo=UTC),
                    open=base + Decimal(str(i)) * Decimal("0.0001"),
                    high=base + Decimal(str(i)) * Decimal("0.0001") + Decimal("0.0003"),
                    low=base + Decimal(str(i)) * Decimal("0.0001") - Decimal("0.0003"),
                    close=base + Decimal(str(i)) * Decimal("0.0001") + Decimal("0.0001"),
                )
                for i in range(25)
            ]
            slipping_fake.set_bars(_SYM, tf, bars)

        slipping_fake.set_tick(_SYM, _tick(30, 0))
        slipping_runner._tick_step(_SYM)
        slipping_fake.set_tick(_SYM, _tick(31, 0))
        slipping_runner._tick_step(_SYM)

        # Emergency close should have closed the bad fill position
        assert len(slipping_fake.positions()) == 0
        assert len(slipping_runner.open_trades) == 0
        assert slipping_runner.state == RunnerState.ARMED
