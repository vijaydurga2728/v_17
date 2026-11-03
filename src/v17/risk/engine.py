from __future__ import annotations

from decimal import Decimal

from v17.backtest.cost import (
    MIN_PIP_SL_BY_SYMBOL,
    PIP_SCALE,
    PIP_VALUE_PER_LOT,
)
from v17.common.dtos import AccountState, Decision, Signal, Trade
from v17.common.types import Side, Symbol
from v17.risk.consistency import would_breach_consistency
from v17.risk.daily_guard import daily_stop_breached
from v17.risk.dd_guard import dd_breached
from v17.risk.ftmo_rules import FTMO_CHALLENGE_10K
from v17.risk.risk_rules import RISK
from v17.risk.sizing import compute_lots


class DefaultRiskEngine:
    def __init__(
        self,
        ftmo: dict[str, object] | None = None,
        risk: dict[str, object] | None = None,
    ) -> None:
        self.ftmo: dict[str, object] = dict(ftmo or FTMO_CHALLENGE_10K)
        self.risk: dict[str, object] = dict(risk or RISK)

    def _pip_value_for(self, symbol: Symbol) -> Decimal:
        # Per-symbol pip value from cost.PIP_VALUE_PER_LOT; fall back to the
        # risk-rules default when a symbol is not mapped (safe for new FX pairs).
        v = PIP_VALUE_PER_LOT.get(symbol)
        if v is not None:
            return v
        return Decimal(str(self.risk["pip_value_per_lot_usd"]))

    def _pip_scale_for(self, symbol: Symbol) -> Decimal:
        return Decimal(str(PIP_SCALE.get(symbol, 10000)))

    def _min_pip_sl_for(self, symbol: Symbol) -> Decimal:
        v = MIN_PIP_SL_BY_SYMBOL.get(symbol)
        if v is not None:
            return v
        return Decimal(str(self.risk["min_pip_sl"]))

    def check(
        self, signal: Signal, account: AccountState, entry: Decimal | None = None
    ) -> Decision:
        if account.kill_active:
            return Decision(allow=False, reason="kill switch active", code="kill_active")
        max_dd = Decimal(str(self.ftmo["max_overall_dd_pct"]))
        if dd_breached(account, max_dd):
            return Decision(allow=False, reason="static DD breached", code="dd_guard")
        soft_stop = Decimal(str(self.ftmo["soft_daily_stop_pct"]))
        if daily_stop_breached(account, soft_stop):
            return Decision(allow=False, reason="daily soft stop", code="daily_stop_locked")
        if account.trades_today >= 2 and account.daily_realized_pnl < Decimal("0"):
            return Decision(allow=False, reason="daily loss limit circuit breaker", code="daily_stop_locked")
        max_positions_raw = self.risk["max_concurrent_positions"]
        max_positions = int(max_positions_raw) if isinstance(max_positions_raw, int) else 1
        if account.open_positions >= max_positions:
            return Decision(allow=False, reason="max positions", code="max_positions")
        max_trades_raw = self.risk["max_trades_per_day"]
        max_trades_today = int(max_trades_raw) if isinstance(max_trades_raw, int) else 3
        if account.trades_today >= max_trades_today:
            return Decision(allow=False, reason="max trades today", code="max_trades_today")
        min_rr = Decimal(str(self.risk["min_rr"]))
        if signal.rr < min_rr:
            return Decision(allow=False, reason=f"rr {signal.rr} < {min_rr}", code="rr_too_low")

        effective_entry = entry if entry is not None else signal.entry
        if signal.side == Side.BUY and effective_entry <= signal.sl:
            return Decision(allow=False, reason="entry at or below sl", code="sl_invalid")
        if signal.side == Side.SELL and effective_entry >= signal.sl:
            return Decision(allow=False, reason="entry at or above sl", code="sl_invalid")

        stop_pips = abs(effective_entry - signal.sl) * self._pip_scale_for(signal.symbol)
        min_pip_sl = self._min_pip_sl_for(signal.symbol)
        if stop_pips < min_pip_sl:
            return Decision(allow=False, reason="stop too tight", code="sl_too_tight")

        target_profit = account.starting_equity * (
            Decimal(str(self.ftmo.get("profit_target_phase1_pct", "10.0"))) / Decimal("100")
        )
        cap = Decimal(str(self.ftmo["consistency_best_day_pct_of_profit"]))
        max_day_profit = target_profit * (cap / Decimal("100"))
        remaining_day_profit = max_day_profit - account.daily_realized_pnl
        if remaining_day_profit <= Decimal("0"):
            return Decision(allow=False, reason="consistency rule", code="consistency_rule")

        std_pct = Decimal(str(self.risk["per_trade_pct"]))
        peak_dd_pct = Decimal("0")
        if account.peak_equity > Decimal("0"):
            peak_dd_pct = (account.peak_equity - account.equity) / account.peak_equity * Decimal("100")
        if account.daily_realized_pnl < Decimal("0") or peak_dd_pct >= Decimal("4.0"):
            std_pct = std_pct * Decimal("0.5")

        safe_profit = remaining_day_profit * Decimal("0.95")
        if signal.rr > Decimal("0"):
            max_pct_for_consistency = (
                safe_profit / (account.equity * signal.rr)
            ) * Decimal("100")
            trade_pct = min(std_pct, max_pct_for_consistency)
        else:
            trade_pct = std_pct

        est_win = (account.equity * trade_pct / Decimal("100")) * signal.rr
        if would_breach_consistency(account, est_win, cap):
            return Decision(allow=False, reason="consistency rule", code="consistency_rule")
        lots = compute_lots(
            equity=account.equity,
            per_trade_pct=trade_pct,
            stop_distance_pips=stop_pips,
            pip_value_per_lot=self._pip_value_for(signal.symbol),
            lot_step=Decimal(str(self.risk["lot_step"])),
            min_lot=Decimal(str(self.risk["min_lot"])),
        )
        if lots <= 0:
            return Decision(allow=False, reason="size below min lot", code="sl_too_tight")
        return Decision(
            allow=True,
            reason="ok",
            code="ok",
            size_lots=lots,
            sl=signal.sl,
            tp=signal.tp,
        )

    def on_fill(self, trade: Trade, account: AccountState) -> AccountState:
        _ = trade
        return account.model_copy(
            update={
                "open_positions": account.open_positions + 1,
                "trades_today": account.trades_today + 1,
            }
        )

    def on_close(self, trade: Trade, account: AccountState) -> AccountState:
        pnl = trade.pnl or Decimal("0")
        new_equity = account.equity + pnl
        new_daily = account.daily_realized_pnl + pnl
        new_total = account.total_realized_pnl + pnl
        new_peak = max(account.peak_equity, new_equity)
        new_best_day = max(account.best_day_pnl, new_daily)
        soft = Decimal(str(self.ftmo["soft_daily_stop_pct"]))
        max_dd = Decimal(str(self.ftmo["max_overall_dd_pct"]))
        locked = (
            account.is_locked_today
            or (new_daily / account.starting_equity * Decimal("100") <= -soft)
            or (account.trades_today >= 2 and new_daily < Decimal("0"))
        )
        kill = account.kill_active or (
            (account.starting_equity - new_equity) / account.starting_equity * Decimal("100")
            >= max_dd
        )
        return account.model_copy(
            update={
                "open_positions": max(0, account.open_positions - 1),
                "equity": new_equity,
                "balance": new_equity,
                "peak_equity": new_peak,
                "daily_realized_pnl": new_daily,
                "total_realized_pnl": new_total,
                "best_day_pnl": new_best_day,
                "is_locked_today": locked,
                "kill_active": kill,
            }
        )
