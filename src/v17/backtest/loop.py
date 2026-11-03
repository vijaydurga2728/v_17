from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pandas as pd

from v17.backtest.cost import PIP_SCALE, ZONE_TOLERANCE_BY_SYMBOL, commission
from v17.backtest.fills import entry_fill, exit_fill_on_bar, pnl_usd
from v17.backtest.precompute import PrecomputedStructure, snapshot_at
from v17.common.dtos import AccountState, Trade
from v17.common.types import Side, SignalId, Symbol, Ticket
from v17.setups.sessions import (
    in_judas_window,
    in_silver_bullet_window,
    window_id_for,
    window_id_for_setup,
)

if TYPE_CHECKING:
    from v17.data.ports import CalendarProvider
    from v17.risk.ports import RiskEngine
    from v17.setups.ports import SetupEngine


def _fresh_account(starting_equity: Decimal) -> AccountState:
    return AccountState(
        equity=starting_equity,
        balance=starting_equity,
        starting_equity=starting_equity,
        peak_equity=starting_equity,
        daily_realized_pnl=Decimal("0"),
        total_realized_pnl=Decimal("0"),
        best_day_pnl=Decimal("0"),
        open_positions=0,
        trading_days_count=0,
        is_locked_today=False,
        kill_active=False,
    )


class EventLoop:
    def __init__(
        self,
        symbol: Symbol,
        setups: list[SetupEngine],
        risk: RiskEngine,
        pre: PrecomputedStructure,
        calendar: CalendarProvider | None = None,
        news_window_min: int = 2,
    ) -> None:
        self.symbol = symbol
        self.setups = setups
        self.risk = risk
        self.pre = pre
        self.calendar = calendar
        self.news_window_min = news_window_min
        self.max_floating_dd_pct: float = 0.0

    def run(  # noqa: PLR0912, PLR0915
        self, start: datetime, end: datetime, starting_equity: Decimal
    ) -> tuple[list[Trade], pd.DataFrame]:
        bars = self.pre.bars_1m
        m = (bars["ts"] >= pd.Timestamp(start)) & (bars["ts"] <= pd.Timestamp(end))
        bars = bars[m].reset_index(drop=True)

        account = _fresh_account(starting_equity)
        trades: list[Trade] = []
        equity_rows: list[tuple[pd.Timestamp, Decimal]] = []
        open_trades: list[Trade] = []
        peak_floating_equity = starting_equity
        max_floating_dd = 0.0
        # Dedupe: one trade per (setup, side) per trading date. Prevents the
        # same ICT setup/zone from firing on 3 consecutive 1m bars.
        # Dedupe: one trade per (setup, side) per day. Window-granular dedupe
        # was tested and REVERTED (EUR 2015-2017 PF 0.89 → 0.69). Day-dedupe
        # was blocking losing re-entries, not winning ones.
        fired_today: set[tuple[str, Side, str | None]] = set()
        prev_date = None
        next_ticket = 1

        bars_len = len(bars)
        if bars_len == 0:
            return [], pd.DataFrame(columns=["date", "equity"])

        ts_list = [t.to_pydatetime() for t in bars["ts"]]
        opens = bars["open"].to_numpy()
        highs = bars["high"].to_numpy()
        lows = bars["low"].to_numpy()

        for i in range(bars_len - 1):
            now = ts_list[i]
            cur_date = now.date()

            # Mark-to-market floating equity on this bar
            if open_trades:
                low_dec = Decimal(str(float(lows[i])))
                high_dec = Decimal(str(float(highs[i])))
                bar_floating_equity = account.equity
                for ot in open_trades:
                    worst_px = low_dec if ot.side == Side.BUY else high_dec
                    raw_float = pnl_usd(
                        ot.side, ot.entry, worst_px, ot.size_lots, symbol=self.symbol
                    )
                    comm_float = commission(ot.size_lots, self.symbol)
                    bar_floating_equity += (raw_float - comm_float)

                peak_floating_equity = max(peak_floating_equity, bar_floating_equity)
                if peak_floating_equity > Decimal("0"):
                    dd_ratio = (peak_floating_equity - bar_floating_equity) / peak_floating_equity
                    dd = float(dd_ratio * Decimal("100"))
                    max_floating_dd = max(max_floating_dd, dd)

                open_dec = Decimal(str(float(opens[i])))
                still_open: list[Trade] = []
                for ot in open_trades:
                    kind, exit_px = exit_fill_on_bar(
                        ot.side, ot.sl, ot.tp, bar_open=open_dec, bar_high=high_dec, bar_low=low_dec
                    )
                    if kind != "none" and exit_px is not None:
                        raw_pnl = pnl_usd(
                            ot.side, ot.entry, exit_px, ot.size_lots, symbol=self.symbol
                        )
                        comm = commission(ot.size_lots, self.symbol)
                        pnl = raw_pnl - comm
                        closed = ot.model_copy(
                            update={
                                "closed_at": now,
                                "close_price": exit_px,
                                "pnl": pnl,
                                "reason": kind,
                            }
                        )
                        trades.append(closed)
                        account = self.risk.on_close(closed, account)
                    else:
                        still_open.append(ot)
                open_trades = still_open

            if prev_date is not None and cur_date != prev_date:
                account = account.model_copy(
                    update={
                        "is_locked_today": False,
                        "daily_realized_pnl": Decimal("0"),
                        "trading_days_count": account.trading_days_count + 1,
                        "trades_today": 0,
                    }
                )
                fired_today = set()
                equity_rows.append((pd.Timestamp(prev_date), account.equity))
            prev_date = cur_date

            if account.kill_active or account.is_locked_today:
                continue

            has_windowed_setups = all(
                hasattr(s, "name") and s.name in ("silver_bullet", "judas_swing")
                for s in self.setups
            )
            in_window = in_silver_bullet_window(now) or in_judas_window(now)
            if has_windowed_setups and not in_window:
                continue

            # News filter — mirror live (runner.py:137). FTMO prohibits trading
            # ±news_window_min around high-impact news for the pair's currencies.
            if self.calendar is not None and self.calendar.is_blackout(
                self.symbol, now, self.news_window_min
            ):
                continue

            # Max 1 concurrent position per symbol
            if open_trades:
                continue

            snap = snapshot_at(self.pre, now)
            recent_bars = bars.iloc[max(0, i - 1440) : i + 1]
            for setup in self.setups:
                sig = setup.evaluate(snap, now, recent_bars)
                if sig is None:
                    continue
                win_id = window_id_for_setup(sig.setup, now)
                if win_id is None or (sig.setup, sig.side, win_id) in fired_today:
                    continue
                next_open = Decimal(str(float(opens[i + 1])))
                entry = entry_fill(
                    sig.side,
                    next_open,
                    self.symbol,
                )
                # Guard 1: fill must be on correct side of SL.
                # If entry >= sig.sl for SELL (or <= for BUY), SL is immediately crossed.
                if sig.side == Side.SELL and entry >= sig.sl:
                    continue
                if sig.side == Side.BUY and entry <= sig.sl:
                    continue

                # Pass actual fill entry to risk.check for exact lot sizing
                dec = self.risk.check(sig, account, entry=entry)
                if not dec.allow or dec.size_lots is None or dec.size_lots <= Decimal("0"):
                    continue

                # Guard 2: fill drift from zone midpoint capped at FULL
                # zone tolerance per symbol. The pick already accepted a zone
                # up to tolerance from price; the fill must stay within the
                # same band or the ICT entry thesis (price at zone) is void.
                pip_scale_sym = Decimal(PIP_SCALE.get(self.symbol, 10000))
                slip_pips = abs(entry - sig.entry) * pip_scale_sym
                slip_cap = ZONE_TOLERANCE_BY_SYMBOL.get(self.symbol, Decimal("10"))
                if slip_pips > slip_cap:
                    continue
                actual_risk_distance = (entry - sig.sl) if sig.side == Side.BUY else (sig.sl - entry)
                if actual_risk_distance <= Decimal("0"):
                    continue
                if sig.setup == "silver_bullet":
                    adj_tp = (
                        entry + (actual_risk_distance * Decimal("2.0"))
                        if sig.side == Side.BUY
                        else entry - (actual_risk_distance * Decimal("2.0"))
                    )
                else:
                    tp_distance = abs(sig.tp - sig.entry)
                    adj_tp = entry + tp_distance if sig.side == Side.BUY else entry - tp_distance

                # Guard 3: post-fill R:R must still pass 1.5.
                if sig.side == Side.SELL:
                    actual_risk = (sig.sl - entry) * pip_scale_sym
                    actual_reward = (entry - adj_tp) * pip_scale_sym
                else:
                    actual_risk = (entry - sig.sl) * pip_scale_sym
                    actual_reward = (adj_tp - entry) * pip_scale_sym
                if actual_risk <= 0:
                    continue
                if actual_reward / actual_risk < Decimal("1.5"):
                    continue
                opened = Trade(
                    ticket=Ticket(next_ticket),
                    signal_id=SignalId(sig.id),
                    symbol=self.symbol,
                    side=sig.side,
                    size_lots=dec.size_lots,
                    entry=entry,
                    sl=sig.sl,
                    tp=adj_tp,
                    opened_at=ts_list[i + 1],
                    reason="open",
                )
                open_trades.append(opened)
                account = self.risk.on_fill(opened, account)
                fired_today.add((sig.setup, sig.side, win_id))
                next_ticket += 1
                break

        if prev_date is not None:
            equity_rows.append((pd.Timestamp(prev_date), account.equity))

        self.max_floating_dd_pct = max_floating_dd
        equity_df = pd.DataFrame(equity_rows, columns=["date", "equity"])
        return trades, equity_df
