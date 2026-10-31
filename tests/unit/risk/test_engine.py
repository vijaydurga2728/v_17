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
