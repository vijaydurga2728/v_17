from datetime import UTC, datetime
from decimal import Decimal

from v17.common.dtos import AccountState, Trade
from v17.common.types import Side, SignalId, Symbol, Ticket
from v17.risk.engine import DefaultRiskEngine


def _fresh() -> AccountState:
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


def _trade(pnl: Decimal) -> Trade:
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


def test_simulated_day_profit_sequence() -> None:
    eng = DefaultRiskEngine()
    acct = _fresh()
    for pnl in (Decimal("1500"), Decimal("1000"), Decimal("-200")):
        acct = eng.on_fill(_trade(pnl), acct)
        acct = eng.on_close(_trade(pnl), acct)
    assert acct.open_positions == 0
    assert acct.daily_realized_pnl == Decimal("2300")
    assert acct.total_realized_pnl == Decimal("2300")
    assert acct.equity == Decimal("102300")
    assert acct.peak_equity == Decimal("102500")  # peak reached after +1500 + 1000
    assert acct.best_day_pnl == Decimal("2500")  # cumulative day pnl peaked after trade 2


def test_simulated_lockout() -> None:
    eng = DefaultRiskEngine()
    acct = _fresh()
    acct = eng.on_fill(_trade(Decimal("-4200")), acct)
    acct = eng.on_close(_trade(Decimal("-4200")), acct)
    assert acct.is_locked_today is True
    assert acct.kill_active is False


def test_simulated_dd_kill() -> None:
    eng = DefaultRiskEngine()
    acct = _fresh()
    acct = eng.on_fill(_trade(Decimal("-10500")), acct)
    acct = eng.on_close(_trade(Decimal("-10500")), acct)
    assert acct.kill_active is True
