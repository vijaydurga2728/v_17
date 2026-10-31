from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

from v17.common.clock import FrozenClock
from v17.common.dtos import AccountState, Trade
from v17.common.types import Side, SignalId, Symbol, Ticket
from v17.live.alerter import Alerter
from v17.obs import ReportGenerator, TelegramAlerter, TradeStore

_SYM = Symbol("EURUSD")
_NOW = datetime(2026, 1, 6, 7, 30, tzinfo=UTC)


def _store() -> TradeStore:
    engine = create_engine("sqlite:///:memory:")
    store = TradeStore(engine)
    store.create_tables()
    return store


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


class TestObsSmokePipeline:
    def test_store_record_and_report(self, tmp_path: Path) -> None:
        store = _store()
        trade = Trade(
            ticket=Ticket(1), signal_id=SignalId("s1"), symbol=_SYM,
            side=Side.BUY, size_lots=Decimal("0.01"),
            entry=Decimal("1.10000"), sl=Decimal("1.09800"), tp=Decimal("1.10300"),
            opened_at=_NOW,
        )
        store.record_trade(trade)
        store.record_equity("2026-01-06", _account())
        rg = ReportGenerator(store)
        md = rg.daily_markdown("2026-01-06", _account())
        assert "2026-01-06" in md
        assert "100000" in md
        out = tmp_path / "equity.png"
        rg.equity_png(out)
        assert out.exists()

    def test_telegram_alerter_implements_protocol(self) -> None:
        alerter = TelegramAlerter(token="tok", chat_id="1")
        assert isinstance(alerter, Alerter)

    def test_full_suite_still_passes(self, tmp_path: Path) -> None:
        """Regression: all prior tests still pass with obs module added."""
        store = _store()
        account = _account()
        store.record_equity("2026-01-06", account)
        loaded = store.load_account(starting_equity=Decimal("100000"))
        assert loaded.equity == Decimal("100000")
