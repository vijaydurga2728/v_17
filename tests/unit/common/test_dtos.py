from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from v17.common.dtos import (
    AccountState,
    BacktestConfig,
    Bar,
    CalendarEvent,
    Decision,
    RunReport,
    Signal,
    StructureSnapshot,
    Sweep,
    Swing,
    Tick,
    Trade,
    Zone,
)
from v17.common.types import TF, Bias, RunId, Side, SignalId, Symbol, Ticket


def _utc(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


def test_bar_requires_tz_aware_utc() -> None:
    with pytest.raises(ValidationError):
        Bar(
            symbol=Symbol("EURUSD"),
            tf=TF.M1,
            ts=datetime(2026, 1, 1),
            open=Decimal("1.1"),
            high=Decimal("1.2"),
            low=Decimal("1.0"),
            close=Decimal("1.15"),
        )


def test_bar_rejects_hl_invariants() -> None:
    with pytest.raises(ValidationError):
        Bar(
            symbol=Symbol("EURUSD"),
            tf=TF.M1,
            ts=_utc(2026, 1, 1),
            open=Decimal("1.1"),
            high=Decimal("0.9"),
            low=Decimal("1.0"),
            close=Decimal("1.0"),
        )


def test_tick_ask_ge_bid() -> None:
    with pytest.raises(ValidationError):
        Tick(
            symbol=Symbol("EURUSD"),
            ts=_utc(2026, 1, 1),
            bid=Decimal("1.11"),
            ask=Decimal("1.10"),
        )


def test_calendar_event_fields() -> None:
    e = CalendarEvent(at=_utc(2026, 1, 1, 13, 30), currency="USD", impact="high", title="NFP")
    assert e.impact == "high"


def test_zone_requires_top_ge_bottom() -> None:
    with pytest.raises(ValidationError):
        Zone(
            kind="fvg",
            side=Side.BUY,
            tf=TF.M15,
            created_at=_utc(2026, 1, 1),
            top=Decimal("1.0"),
            bottom=Decimal("1.1"),
        )


def test_swing_fields() -> None:
    s = Swing(kind="bos", side=Side.BUY, tf=TF.M15, at=_utc(2026, 1, 1), price=Decimal("1.1"))
    assert s.kind == "bos"


def test_sweep_fields() -> None:
    s = Sweep(kind="bsl", tf=TF.M15, at=_utc(2026, 1, 1), level=Decimal("1.2"))
    assert s.kind == "bsl"


def test_snapshot_round_trip() -> None:
    snap = StructureSnapshot(
        symbol=Symbol("EURUSD"),
        at=_utc(2026, 1, 1),
        bias=Bias.BULL,
        zones=[],
        swings=[],
        sweeps=[],
    )
    assert snap.bias == Bias.BULL


def test_signal_rr_too_low_rejected() -> None:
    with pytest.raises(ValidationError):
        Signal(
            id=SignalId("abc"),
            symbol=Symbol("EURUSD"),
            setup="silver_bullet",
            side=Side.BUY,
            at=_utc(2026, 1, 1, 8, 30),
            entry=Decimal("1.1000"),
            sl=Decimal("1.0990"),
            tp=Decimal("1.1010"),
            rr=Decimal("1.0"),
            confluence={"bias": True, "fvg": True, "ob": True, "mss": True, "sweep": True},
        )


def test_signal_minimal_valid() -> None:
    s = Signal(
        id=SignalId("abc"),
        symbol=Symbol("EURUSD"),
        setup="silver_bullet",
        side=Side.BUY,
        at=_utc(2026, 1, 1, 8, 30),
        entry=Decimal("1.1000"),
        sl=Decimal("1.0990"),
        tp=Decimal("1.1015"),
        rr=Decimal("1.5"),
        confluence={"bias": True, "fvg": True, "ob": True, "mss": True, "sweep": True},
    )
    assert s.rr == Decimal("1.5")


def test_signal_confluence_wrong_keys_rejected() -> None:
    with pytest.raises(ValidationError):
        Signal(
            id=SignalId("abc"),
            symbol=Symbol("EURUSD"),
            setup="silver_bullet",
            side=Side.BUY,
            at=_utc(2026, 1, 1, 8, 30),
            entry=Decimal("1.1000"),
            sl=Decimal("1.0990"),
            tp=Decimal("1.1015"),
            rr=Decimal("1.5"),
            confluence={"bias": True},
        )


def test_decision_pass() -> None:
    d = Decision(
        allow=True,
        reason="ok",
        code="ok",
        size_lots=Decimal("0.10"),
        sl=Decimal("1.1"),
        tp=Decimal("1.12"),
    )
    assert d.allow is True


def test_decision_reject() -> None:
    d = Decision(allow=False, reason="daily stop", code="daily_stop_locked")
    assert d.size_lots is None


def test_account_state_round_trip() -> None:
    a = AccountState(
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
    assert a.equity == Decimal("100000")


def test_trade_fields() -> None:
    t = Trade(
        ticket=Ticket(1),
        signal_id=SignalId("abc"),
        symbol=Symbol("EURUSD"),
        side=Side.BUY,
        size_lots=Decimal("0.1"),
        entry=Decimal("1.1"),
        sl=Decimal("1.09"),
        tp=Decimal("1.115"),
        opened_at=_utc(2026, 1, 1, 8, 0),
        closed_at=_utc(2026, 1, 1, 10, 0),
        close_price=Decimal("1.115"),
        pnl=Decimal("150"),
        reason="tp",
    )
    assert t.pnl == Decimal("150")


def test_backtest_config_defaults() -> None:
    cfg = BacktestConfig(
        symbol=Symbol("EURUSD"),
        start=_utc(2024, 1, 1),
        end=_utc(2024, 12, 31),
    )
    assert cfg.starting_equity == Decimal("10000")
    assert cfg.seed == 42


def test_run_report_fields() -> None:
    cfg = BacktestConfig(
        symbol=Symbol("EURUSD"),
        start=_utc(2024, 1, 1),
        end=_utc(2024, 12, 31),
    )
    r = RunReport(
        run_id=RunId("x"),
        config=cfg,
        trades=100,
        winrate=0.55,
        pf=1.8,
        sharpe=2.1,
        max_dd_pct=5.5,
        net_pnl=Decimal("10000"),
    )
    assert r.pf == 1.8
