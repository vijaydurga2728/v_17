from datetime import UTC, datetime
from decimal import Decimal

from v17.common.dtos import AccountState, Signal, Trade
from v17.common.types import Side, SignalId, Symbol, Ticket
from v17.risk.engine import DefaultRiskEngine


def _acct(**over: object) -> AccountState:
    base = {
        "equity": Decimal("100000"),
        "balance": Decimal("100000"),
        "starting_equity": Decimal("100000"),
        "peak_equity": Decimal("100000"),
        "daily_realized_pnl": Decimal("0"),
        "total_realized_pnl": Decimal("0"),
        "best_day_pnl": Decimal("0"),
        "open_positions": 0,
        "trading_days_count": 0,
        "is_locked_today": False,
        "kill_active": False,
    }
    base.update(over)
    return AccountState(**base)  # type: ignore[arg-type]


def _signal(
    entry: str = "1.1000", sl: str = "1.0990", tp: str = "1.1015", rr: str = "1.5"
) -> Signal:
    return Signal(
        id=SignalId("abc"),
        symbol=Symbol("EURUSD"),
        setup="silver_bullet",
        side=Side.BUY,
        at=datetime(2026, 1, 1, 8, 30, tzinfo=UTC),
        entry=Decimal(entry),
        sl=Decimal(sl),
        tp=Decimal(tp),
        rr=Decimal(rr),
        confluence={"bias": True, "fvg": True, "ob": True, "mss": True, "sweep": True},
    )


def _trade(pnl: Decimal | None) -> Trade:
    return Trade(
        ticket=Ticket(1),
        signal_id=SignalId("abc"),
        symbol=Symbol("EURUSD"),
        side=Side.BUY,
        size_lots=Decimal("0.1"),
        entry=Decimal("1.1"),
        sl=Decimal("1.09"),
        tp=Decimal("1.115"),
        opened_at=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
        closed_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        close_price=Decimal("1.115"),
        pnl=pnl,
        reason="tp",
    )


def test_kill_rejects_first() -> None:
    d = DefaultRiskEngine().check(_signal(), _acct(kill_active=True))
    assert d.allow is False and d.code == "kill_active"


def test_dd_rejects() -> None:
    d = DefaultRiskEngine().check(_signal(), _acct(equity=Decimal("90000")))
    assert d.code == "dd_guard"


def test_daily_stop_rejects() -> None:
    d = DefaultRiskEngine().check(
        _signal(), _acct(daily_realized_pnl=Decimal("-4000"))
    )
    assert d.code == "daily_stop_locked"


def test_max_positions_rejects() -> None:
    d = DefaultRiskEngine().check(_signal(), _acct(open_positions=3))
    assert d.code == "max_positions"


def test_max_trades_today_rejects() -> None:
    d = DefaultRiskEngine().check(_signal(), _acct(trades_today=3))
    assert d.code == "max_trades_today"


def test_sl_too_tight_rejects() -> None:
    # 1 pip stop
    d = DefaultRiskEngine().check(_signal(sl="1.0999"), _acct())
    assert d.code == "sl_too_tight"


def test_pass_sizes_lots() -> None:
    d = DefaultRiskEngine().check(_signal(), _acct())
    assert d.allow is True
    assert d.size_lots is not None and d.size_lots > Decimal("0")
    assert d.code == "ok"


def test_on_fill_increments() -> None:
    acct = _acct()
    acct2 = DefaultRiskEngine().on_fill(_trade(None), acct)
    assert acct2.open_positions == 1


def test_on_close_win_updates_pnl() -> None:
    acct = _acct(open_positions=1)
    acct2 = DefaultRiskEngine().on_close(_trade(Decimal("1500")), acct)
    assert acct2.open_positions == 0
    assert acct2.equity == Decimal("101500")
    assert acct2.daily_realized_pnl == Decimal("1500")
    assert acct2.best_day_pnl == Decimal("1500")
    assert acct2.peak_equity == Decimal("101500")


def test_on_close_big_loss_locks_day() -> None:
    acct = _acct(open_positions=1)
    acct2 = DefaultRiskEngine().on_close(_trade(Decimal("-4200")), acct)
    assert acct2.is_locked_today is True


def test_on_close_dd_breach_kills() -> None:
    acct = _acct(open_positions=1, equity=Decimal("91000"))
    acct2 = DefaultRiskEngine().on_close(_trade(Decimal("-1500")), acct)
    assert acct2.kill_active is True


def test_multi_symbol_sizing_index_and_jpy() -> None:
    engine = DefaultRiskEngine()
    acct = _acct()

    # NAS100 (USATECHIDXUSD): 10 point stop, $1/point/lot -> should size lots appropriately
    confluence_mock = {"bias": True, "fvg": True, "ob": True, "mss": True, "sweep": True}
    sig_nas = Signal(
        id=SignalId("nas1"),
        symbol=Symbol("USATECHIDXUSD"),
        setup="silver_bullet",
        side=Side.BUY,
        at=datetime(2026, 1, 1, 14, 30, tzinfo=UTC),
        entry=Decimal("19000.00"),
        sl=Decimal("18990.00"),
        tp=Decimal("19030.00"),
        rr=Decimal("3.0"),
        confluence=confluence_mock,
    )
    d_nas = engine.check(sig_nas, acct)
    assert d_nas.allow is True
    assert d_nas.size_lots is not None and d_nas.size_lots > Decimal("0")

    # USDJPY: 20 pip stop (0.20 price units), pip_scale=100
    sig_jpy = Signal(
        id=SignalId("jpy1"),
        symbol=Symbol("USDJPY"),
        setup="silver_bullet",
        side=Side.BUY,
        at=datetime(2026, 1, 1, 8, 30, tzinfo=UTC),
        entry=Decimal("150.20"),
        sl=Decimal("150.00"),
        tp=Decimal("150.60"),
        rr=Decimal("2.0"),
        confluence=confluence_mock,
    )
    d_jpy = engine.check(sig_jpy, acct)
    assert d_jpy.allow is True
    assert d_jpy.size_lots is not None and d_jpy.size_lots > Decimal("0")


def test_circuit_breaker_consecutive_losses_locks_day() -> None:
    engine = DefaultRiskEngine()
    # 2 trades today, daily realized PnL is negative
    acct = _acct(trades_today=2, daily_realized_pnl=Decimal("-1000"))
    d = engine.check(_signal(), acct)
    assert d.allow is False
    assert d.code == "daily_stop_locked"


def test_circuit_breaker_drawdown_adaptive_sizing() -> None:
    engine = DefaultRiskEngine()
    acct_clean = _acct()
    d_clean = engine.check(_signal(), acct_clean)
    assert d_clean.allow is True
    assert d_clean.size_lots is not None

    # Account with daily loss -> sizes lots at 50%
    acct_loss = _acct(daily_realized_pnl=Decimal("-500"), trades_today=1)
    d_loss = engine.check(_signal(), acct_loss)
    assert d_loss.allow is True
    assert d_loss.size_lots is not None
    # Sizing should be approximately half of clean
    assert d_loss.size_lots < d_clean.size_lots
