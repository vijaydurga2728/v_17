from __future__ import annotations

from typing import Protocol

from v17.common.dtos import AccountState, Decision, Signal, Trade


class RiskEngine(Protocol):
    def check(
        self, signal: Signal, account: AccountState, entry: Decimal | None = None
    ) -> Decision: ...

    def on_fill(self, trade: Trade, account: AccountState) -> AccountState: ...

    def on_close(self, trade: Trade, account: AccountState) -> AccountState: ...
