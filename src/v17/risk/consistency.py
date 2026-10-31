from __future__ import annotations

from decimal import Decimal

from v17.common.dtos import AccountState


def would_breach_consistency(
    account: AccountState,
    est_win: Decimal,
    best_day_pct_cap: Decimal,
    target_profit_pct: Decimal = Decimal("10.0"),
) -> bool:
    # FTMO consistency rule ensures no single day accounts for more than
    # best_day_pct_cap (e.g., 30%) of the challenge target profit.
    new_today = account.daily_realized_pnl + est_win
    if new_today <= 0:
        return False
    target_profit = account.starting_equity * (target_profit_pct / Decimal("100"))
    max_day_profit = target_profit * (best_day_pct_cap / Decimal("100"))
    if new_today >= max_day_profit:
        return True
    new_total = account.total_realized_pnl + est_win
    if new_total >= target_profit:
        return (new_today / new_total * Decimal("100")) > best_day_pct_cap
    return False
