from decimal import Decimal

from v17.common.dtos import AccountState
from v17.risk.dd_guard import dd_breached


def _acct(equity: Decimal, kill: bool = False) -> AccountState:
    return AccountState(
        equity=equity,
        balance=equity,
        starting_equity=Decimal("100000"),
        peak_equity=Decimal("100000"),
        daily_realized_pnl=Decimal("0"),
        total_realized_pnl=equity - Decimal("100000"),
        best_day_pnl=Decimal("0"),
        open_positions=0,
        trading_days_count=1,
        is_locked_today=False,
        kill_active=kill,
    )


def test_within_dd() -> None:
    assert dd_breached(_acct(Decimal("91000")), Decimal("10.0")) is False


def test_at_dd_limit() -> None:
    assert dd_breached(_acct(Decimal("90000")), Decimal("10.0")) is True


def test_kill_sticky() -> None:
    assert dd_breached(_acct(Decimal("100000"), kill=True), Decimal("10.0")) is True
