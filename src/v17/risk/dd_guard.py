from __future__ import annotations

from decimal import Decimal

from v17.common.dtos import AccountState


def dd_breached(account: AccountState, max_dd_pct: Decimal) -> bool:
    if account.kill_active:
        return True
    dd_pct = (account.starting_equity - account.equity) / account.starting_equity * Decimal("100")
    return dd_pct >= max_dd_pct
