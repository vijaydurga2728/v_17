from __future__ import annotations

from decimal import Decimal

from v17.common.dtos import AccountState


def daily_stop_breached(account: AccountState, soft_stop_pct: Decimal) -> bool:
    if account.is_locked_today:
        return True
    pnl_pct = account.daily_realized_pnl / account.starting_equity * Decimal("100")
    return pnl_pct <= -soft_stop_pct
