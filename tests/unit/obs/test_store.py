from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine

from v17.common.dtos import AccountState, Trade
from v17.common.types import Side, SignalId, Symbol, Ticket
from v17.obs.store import TradeStore, create_engine_for_path


_SYM = Symbol("EURUSD")
_NOW = datetime(2026, 1, 6, 7, 30, tzinfo=UTC)


def _engine():
    return create_engine("sqlite:///:memory:", echo=False)


def _store():
    engine = _engine()
    store = TradeStore(engine)
    store.create_tables()
    return store


def _trade() -> Trade:
    return Trade(
        ticket=Ticket(1),
        signal_id=SignalId("sig-001"),
        symbol=_SYM,
        side=Side.BUY,
        size_lots=Decimal("0.01"),
        entry=Decimal("1.10000"),
        sl=Decimal("1.09800"),
        tp=Decimal("1.10300"),
        opened_at=_NOW,
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


class TestTradeStoreRecordTrade:
    def test_record_and_retrieve(self) -> None:
        store = _store()
        trade = _trade()
        store.record_trade(trade)
        rows = store.trades_for_date("2026-01-06")
        assert len(rows) == 1
        assert rows[0].ticket == 1
        assert rows[0].symbol == "EURUSD"

    def test_duplicate_ticket_ignored(self) -> None:
        store = _store()
        trade = _trade()
        store.record_trade(trade)
        store.record_trade(trade)  # must not raise or duplicate
        rows = store.trades_for_date("2026-01-06")
        assert len(rows) == 1


class TestTradeStoreUpdateClose:
    def test_update_close_sets_fields(self) -> None:
        store = _store()
        store.record_trade(_trade())
        store.update_close(
            ticket=Ticket(1),
            closed_at=datetime(2026, 1, 6, 8, 0, tzinfo=UTC),
            close_price=Decimal("1.10300"),
            pnl=Decimal("30.00"),
            reason="tp",
        )
        rows = store.trades_for_date("2026-01-06")
        assert rows[0].pnl == "30.00"
        assert rows[0].reason == "tp"


class TestTradeStoreEquity:
    def test_record_equity(self) -> None:
        store = _store()
        store.record_equity("2026-01-06", _account())
        hist = store.equity_history()
        assert len(hist) == 1
        assert hist[0].date == "2026-01-06"

    def test_upsert_equity_same_date(self) -> None:
        store = _store()
        store.record_equity("2026-01-06", _account())
        updated = _account().model_copy(update={"equity": Decimal("100100")})
        store.record_equity("2026-01-06", updated)
        hist = store.equity_history()
        assert len(hist) == 1
        assert hist[0].equity == "100100"


class TestTradeStoreLoadAccount:
    def test_load_account_no_trades(self) -> None:
        store = _store()
        account = store.load_account(starting_equity=Decimal("100000"))
        assert account.equity == Decimal("100000")
        assert account.open_positions == 0

    def test_load_account_with_open_trade(self) -> None:
        store = _store()
        store.record_trade(_trade())  # open trade (no closed_at)
        account = store.load_account(starting_equity=Decimal("100000"))
        assert account.open_positions == 1


class TestTradeStoreErrors:
    def test_record_error(self) -> None:
        store = _store()
        store.record_error("critical", "gateway disconnected", {"symbol": "EURUSD"})
        # no assertion needed — just must not raise


class TestCreateEngineForPath:
    def test_creates_file(self, tmp_path) -> None:
        db_path = tmp_path / "v17.db"
        engine = create_engine_for_path(db_path)
        store = TradeStore(engine)
        store.create_tables()
        assert db_path.exists()
