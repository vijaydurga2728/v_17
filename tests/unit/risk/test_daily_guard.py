from decimal import Decimal

from v17.common.dtos import AccountState
from v17.risk.daily_guard import daily_stop_breached


def _acct(pnl: Decimal, locked: bool = False) -> AccountState:
    return AccountState(
        equity=Decimal("100000") + pnl,
        balance=Decimal("100000") + pnl,
        starting_equity=Decimal("100000"),
        peak_equity=Decimal("100000"),
        daily_realized_pnl=pnl,
        total_realized_pnl=pnl,
        best_day_pnl=Decimal("0"),
        open_positions=0,
        trading_days_count=1,
        is_locked_today=locked,
        kill_active=False,
    )


def test_within_limit() -> None:
    assert daily_stop_breached(_acct(Decimal("-3999")), Decimal("4.0")) is False


def test_at_soft_stop() -> None:
    assert daily_stop_breached(_acct(Decimal("-4000")), Decimal("4.0")) is True


def test_lockout_sticky() -> None:
    assert daily_stop_breached(_acct(Decimal("0"), locked=True), Decimal("4.0")) is True
