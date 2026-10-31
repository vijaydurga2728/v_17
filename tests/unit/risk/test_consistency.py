from decimal import Decimal

from v17.common.dtos import AccountState
from v17.risk.consistency import would_breach_consistency


def _acct(day_pnl: Decimal, total: Decimal, best: Decimal) -> AccountState:
    return AccountState(
        equity=Decimal("100000") + total,
        balance=Decimal("100000") + total,
        starting_equity=Decimal("100000"),
        peak_equity=Decimal("100000"),
        daily_realized_pnl=day_pnl,
        total_realized_pnl=total,
        best_day_pnl=best,
        open_positions=0,
        trading_days_count=1,
        is_locked_today=False,
        kill_active=False,
    )


def test_within_cap() -> None:
    a = _acct(Decimal("500"), Decimal("9500"), Decimal("1000"))
    assert would_breach_consistency(a, Decimal("500"), Decimal("30.0")) is False


def test_breach() -> None:
    a = _acct(Decimal("1000"), Decimal("100"), Decimal("0"))
    assert would_breach_consistency(a, Decimal("2000"), Decimal("30.0")) is True


def test_no_profit_no_rule() -> None:
    a = _acct(Decimal("-500"), Decimal("-1000"), Decimal("0"))
    assert would_breach_consistency(a, Decimal("500"), Decimal("30.0")) is False


def test_past_best_day_does_not_deadlock_subsequent_trading() -> None:
    # A past day had $3,351 profit, but subsequent drawdown brought total profit down to $510.
    # Today is a new day (daily_realized_pnl = 0).
    # A standard 1.5R trade (est_win = $1,500) must be allowed so the account can continue trading.
    a = _acct(Decimal("0"), Decimal("510"), Decimal("3351"))
    assert would_breach_consistency(a, Decimal("1500"), Decimal("30.0")) is False
