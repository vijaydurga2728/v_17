from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from v17.common.dtos import AccountState
from v17.obs.report import ReportGenerator
from v17.obs.store import TradeStore


def _store() -> TradeStore:
    engine = create_engine("sqlite:///:memory:")
    store = TradeStore(engine)
    store.create_tables()
    return store


def _account() -> AccountState:
    return AccountState(
        equity=Decimal("100350"),
        balance=Decimal("100350"),
        starting_equity=Decimal("100000"),
        peak_equity=Decimal("100350"),
        daily_realized_pnl=Decimal("350"),
        total_realized_pnl=Decimal("350"),
        best_day_pnl=Decimal("350"),
        open_positions=0,
        trading_days_count=1,
        is_locked_today=False,
        kill_active=False,
    )


class TestDailyMarkdown:
    def test_returns_string(self) -> None:
        store = _store()
        rg = ReportGenerator(store)
        md = rg.daily_markdown("2026-01-06", _account())
        assert isinstance(md, str)
        assert len(md) > 0

    def test_contains_date(self) -> None:
        store = _store()
        rg = ReportGenerator(store)
        md = rg.daily_markdown("2026-01-06", _account())
        assert "2026-01-06" in md

    def test_contains_equity(self) -> None:
        store = _store()
        rg = ReportGenerator(store)
        md = rg.daily_markdown("2026-01-06", _account())
        assert "100350" in md

    def test_contains_daily_pnl(self) -> None:
        store = _store()
        rg = ReportGenerator(store)
        md = rg.daily_markdown("2026-01-06", _account())
        assert "350" in md


class TestEquityPng:
    def test_creates_file(self, tmp_path: Path) -> None:
        store = _store()
        store.record_equity("2026-01-04", _account())
        store.record_equity("2026-01-05", _account())
        store.record_equity("2026-01-06", _account())
        rg = ReportGenerator(store)
        out = tmp_path / "equity.png"
        rg.equity_png(out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_no_data_creates_empty_png(self, tmp_path: Path) -> None:
        store = _store()
        rg = ReportGenerator(store)
        out = tmp_path / "equity.png"
        rg.equity_png(out)  # no data — must not raise
        assert out.exists()
