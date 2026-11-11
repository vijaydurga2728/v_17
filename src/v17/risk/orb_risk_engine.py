"""ORB-pipeline FTMO circuit breakers.

Float-based. Independent from legacy DefaultRiskEngine (Decimal).

Soft stop: equity drops >=3% below start-of-day → freeze engines until next
NY midnight (caller advances via start_of_day).
Hard freeze: peak-equity drawdown >=8% → permanent freeze.
"""
from __future__ import annotations

from v17.setups.orb_constants import DAILY_LOSS_SOFT_STOP, TOTAL_LOSS_HARD_FREEZE


_NS_PER_DAY = 86_400_000_000_000


class ORBRiskEngine:
    def __init__(self, starting_equity: float):
        self._equity: float = float(starting_equity)
        self._peak: float = float(starting_equity)
        self._initial: float = float(starting_equity)
        self._day_start_equity: float = float(starting_equity)
        self._permanently_frozen: bool = False
        self._daily_frozen_until_day_ns: int | None = None
        self._current_day_ns: int | None = None

    @property
    def equity(self) -> float:
        return self._equity

    def start_of_day(self, day_ns: int) -> None:
        self._current_day_ns = int(day_ns)
        if (
            self._daily_frozen_until_day_ns is not None
            and self._current_day_ns >= self._daily_frozen_until_day_ns
        ):
            self._daily_frozen_until_day_ns = None
        self._day_start_equity = self._equity

    def update_peak_equity(self, equity: float) -> None:
        self._peak = max(self._peak, float(equity))

    def on_trade_close(self, pnl_cash: float, trade_date_utc_ns: int) -> None:
        self._equity += float(pnl_cash)
        self._peak = max(self._peak, self._equity)
        if self._day_start_equity > 0:
            day_pnl_pct = (self._equity - self._day_start_equity) / self._day_start_equity
            if day_pnl_pct <= -DAILY_LOSS_SOFT_STOP:
                self._daily_frozen_until_day_ns = int(trade_date_utc_ns) + _NS_PER_DAY
        if self._peak > 0:
            total_dd_pct = (self._peak - self._equity) / self._peak
            if total_dd_pct >= TOTAL_LOSS_HARD_FREEZE:
                self._permanently_frozen = True

    def allow_trade(self) -> bool:
        if self._permanently_frozen:
            return False
        if self._daily_frozen_until_day_ns is not None:
            return False
        return True
