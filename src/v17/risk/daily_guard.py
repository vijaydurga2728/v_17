from __future__ import annotations

from decimal import Decimal

from v17.common.dtos import AccountState


def daily_stop_breached(account: AccountState, soft_stop_pct: Decimal) -> bool:
    if account.is_locked_today:
        return True
    ref_equity = account.day_start_equity if account.day_start_equity is not None else account.starting_equity
    # FTMO Daily loss measures drop from day start equity including open floating losses
    # as well as closed realized PnL:
    equity_drop = ref_equity - account.equity
    realized_drop = -account.daily_realized_pnl
    worst_drop = max(equity_drop, realized_drop)
    drop_pct = worst_drop / account.starting_equity * Decimal("100")
    return drop_pct >= soft_stop_pct
