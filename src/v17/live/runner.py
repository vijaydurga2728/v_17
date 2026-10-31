from __future__ import annotations

import contextlib
from decimal import Decimal
from pathlib import Path

import structlog

from v17.common.clock import Clock
from v17.common.dtos import AccountState, OrderRequest, Tick, Trade
from v17.common.errors import V17StructureError
from v17.common.types import TF, SignalId, Symbol
from v17.data.ports import CalendarProvider
from v17.live.alerter import Alerter
from v17.live.bar_builder import BarBuilder
from v17.live.kill_switch import read_kill
from v17.live.preflight import PreFlight
from v17.live.state_machine import RunnerState
from v17.mt5.protocol import TradeGateway
from v17.risk.ports import RiskEngine
from v17.setups.ports import SetupEngine
from v17.structure.ports import StructureEngine

_log = structlog.get_logger(__name__)


class LiveRunner:
    def __init__(
        self,
        gateway: TradeGateway,
        structure_engine: StructureEngine,
        setup_engines: list[SetupEngine],
        risk_engine: RiskEngine,
        calendar: CalendarProvider,
        alerter: Alerter,
        state_root: Path,
        symbols: list[Symbol],
        clock: Clock,
        initial_account: AccountState,
    ) -> None:
        self._gateway = gateway
        self._structure_engine = structure_engine
        self._setup_engines = setup_engines
        self._risk_engine = risk_engine
        self._calendar = calendar
        self._alerter = alerter
        self._state_root = state_root
        self._symbols = symbols
        self._clock = clock
        self._account = initial_account
        self._state = RunnerState.IDLE
        self._open_trade: Trade | None = None
        self._bar_builders: dict[Symbol, BarBuilder] = {
            sym: BarBuilder(sym) for sym in symbols
        }

    @property
    def state(self) -> RunnerState:
        return self._state

    def _killzone_start(self) -> None:
        self._state = RunnerState.PRE_FLIGHT
        pf = PreFlight(
            self._state_root,
            self._gateway,
            self._calendar,
            self._symbols[0],
            self._clock,
        )
        result = pf.run()
        if not result.ok:
            for r in result.reasons:
                _log.error("preflight_failed", reason=r)
            self._alerter.send(
                f"PreFlight FAILED: {'; '.join(result.reasons)}", level="error"
            )
            self._state = RunnerState.IDLE
            return
        # Day reset at killzone open: trades_today, is_locked_today, daily_realized_pnl.
        self._account = self._account.model_copy(
            update={
                "trades_today": 0,
                "is_locked_today": False,
                "daily_realized_pnl": Decimal("0"),
            }
        )
        self._state = RunnerState.ARMED
        self._reconcile()
        _log.info("killzone_armed")
        self._alerter.send("Killzone ARMED — listening for setups")

    def _killzone_stop(self) -> None:
        _log.info("killzone_stop")
        self._alerter.send("Killzone END — going idle")
        self._state = RunnerState.IDLE

    def start(self) -> None:
        from apscheduler.schedulers.blocking import (  # type: ignore[import-untyped]
            BlockingScheduler,
        )
        from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

        _london = "Europe/London"
        scheduler = BlockingScheduler(timezone=_london)
        scheduler.add_job(
            self._killzone_start,
            CronTrigger(day_of_week="mon-fri", hour=6, minute=50, timezone=_london),
        )
        scheduler.add_job(
            self._killzone_stop,
            CronTrigger(day_of_week="mon-fri", hour=10, minute=5, timezone=_london),
        )
        scheduler.add_job(self._tick_poll, "interval", seconds=1)
        with contextlib.suppress(KeyboardInterrupt, SystemExit):
            scheduler.start()

    def stop(self) -> None:
        self._state = RunnerState.IDLE

    def _tick_step(self, symbol: Symbol) -> None:
        if read_kill(self._state_root):
            _log.critical("kill_switch_detected")
            self._alerter.send("KILL sentinel detected — going IDLE", level="critical")
            self._state = RunnerState.IDLE
            return

        tick = self._gateway.tick(symbol)
        if tick is None:
            return

        if self._state == RunnerState.ARMED:
            self._process_armed(symbol, tick)
        elif self._state in (RunnerState.IN_TRADE, RunnerState.MANAGED):
            self._process_in_trade(symbol, tick)

    def _process_armed(self, symbol: Symbol, tick: Tick) -> None:
        if self._calendar.is_blackout(symbol, tick.ts):
            return

        bars = self._bar_builders[symbol].on_tick(tick, self._gateway)
        if bars is None:
            return

        try:
            snap = self._structure_engine.analyze(bars)
        except V17StructureError as exc:
            _log.warning("structure_error", error=str(exc))
            return

        bars_1m = bars[TF.M1]
        for engine in self._setup_engines:
            signal = engine.evaluate(snap, tick.ts, bars_1m)
            if signal is None:
                continue

            decision = self._risk_engine.check(signal, self._account)
            if not decision.allow:
                _log.info("risk_rejected", code=decision.code, reason=decision.reason)
                continue

            assert decision.size_lots is not None
            order = OrderRequest(
                symbol=signal.symbol,
                side=signal.side,
                size_lots=decision.size_lots,
                sl=signal.sl,
                tp=signal.tp,
                comment=f"{signal.setup}:{signal.id}",
            )
            result = self._gateway.order_send(order)
            if not result.ok:
                _log.error(
                    "order_rejected",
                    code=result.error_code,
                    msg=result.error_message,
                )
                continue

            assert result.ticket is not None
            assert result.filled_price is not None
            assert result.filled_at is not None
            trade = Trade(
                ticket=result.ticket,
                signal_id=signal.id,
                symbol=signal.symbol,
                side=signal.side,
                size_lots=decision.size_lots,
                entry=result.filled_price,
                sl=signal.sl,
                tp=signal.tp,
                opened_at=result.filled_at,
            )
            self._open_trade = trade
            self._account = self._risk_engine.on_fill(trade, self._account)
            self._state = RunnerState.IN_TRADE
            _log.info(
                "trade_opened",
                setup=signal.setup,
                side=signal.side.value,
                symbol=str(signal.symbol),
                entry=str(result.filled_price),
                ticket=result.ticket,
            )
            self._alerter.send(
                f"ENTRY {signal.setup} {signal.side} {signal.symbol} "
                f"@{result.filled_price} SL={signal.sl} TP={signal.tp}"
            )
            break

    def _process_in_trade(self, symbol: Symbol, tick: Tick) -> None:
        if self._open_trade is None:
            self._state = RunnerState.ARMED
            return

        positions = self._gateway.positions()
        open_tickets = {p.ticket for p in positions}

        if self._open_trade.ticket not in open_tickets:
            closed = self._open_trade.model_copy(
                update={"closed_at": tick.ts, "reason": "sl_or_tp"}
            )
            self._account = self._risk_engine.on_close(closed, self._account)
            _log.info(
                "trade_closed",
                ticket=self._open_trade.ticket,
                symbol=str(self._open_trade.symbol),
            )
            self._alerter.send(
                f"CLOSE {self._open_trade.symbol} ticket={self._open_trade.ticket}"
            )
            self._open_trade = None
            self._state = RunnerState.ARMED

    def _tick_poll(self) -> None:
        for symbol in self._symbols:
            self._tick_step(symbol)

    def _reconcile(self) -> None:
        positions = self._gateway.positions()
        for pos in positions:
            if pos.symbol in self._symbols:
                trade = Trade(
                    ticket=pos.ticket,
                    signal_id=SignalId("reconciled"),
                    symbol=pos.symbol,
                    side=pos.side,
                    size_lots=pos.size_lots,
                    entry=pos.entry,
                    sl=pos.sl,
                    tp=pos.tp,
                    opened_at=pos.opened_at,
                )
                self._open_trade = trade
                self._account = self._account.model_copy(
                    update={"open_positions": 1}
                )
                self._state = RunnerState.IN_TRADE
                _log.info(
                    "reconciled_open_trade",
                    ticket=pos.ticket,
                    symbol=str(pos.symbol),
                )
                return
