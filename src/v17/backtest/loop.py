from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pandas as pd

from v17.backtest.cost import commission
from v17.backtest.fills import entry_fill, exit_fill_on_bar, pnl_usd
from v17.backtest.precompute import PrecomputedStructure, snapshot_at
from v17.common.dtos import AccountState, Trade
from v17.common.types import Side, SignalId, Symbol, Ticket
from v17.setups.sessions import in_judas_window, in_silver_bullet_window

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
        fired_today: set[tuple[str, Side]] = set()
        prev_date = None
        next_ticket = 1

        for i in range(len(bars) - 1):
            bar = bars.iloc[i]
            now = bar["ts"].to_pydatetime()
            cur_date = bar["ts"].date()

            # Mark-to-market floating equity on this bar
            bar_floating_equity = account.equity
            for ot in open_trades:
                worst_px = (
                    Decimal(str(float(bar["low"])))
                    if ot.side == Side.BUY
                    else Decimal(str(float(bar["high"])))
                )
                raw_float = pnl_usd(ot.side, ot.entry, worst_px, ot.size_lots)
                comm_float = commission(ot.size_lots, self.symbol)
                bar_floating_equity += (raw_float - comm_float)

            if bar_floating_equity > peak_floating_equity:
                peak_floating_equity = bar_floating_equity
            if peak_floating_equity > Decimal("0"):
                dd = float((peak_floating_equity - bar_floating_equity) / peak_floating_equity * Decimal("100"))
                if dd > max_floating_dd:
                    max_floating_dd = dd

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

            # Close any open trades hit by this bar.
            still_open: list[Trade] = []
            for ot in open_trades:
                kind, exit_px = exit_fill_on_bar(ot.side, ot.sl, ot.tp, bar)
                if kind != "none" and exit_px is not None:
                    raw_pnl = pnl_usd(ot.side, ot.entry, exit_px, ot.size_lots)
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

            if account.kill_active or account.is_locked_today:
                continue

            # News filter — mirror live (runner.py:137). FTMO prohibits trading
            # ±news_window_min around high-impact news for the pair's currencies.
            if self.calendar is not None and self.calendar.is_blackout(
                self.symbol, now, self.news_window_min
            ):
                continue

            has_windowed_setups = all(
                hasattr(s, "name") and s.name in ("silver_bullet", "judas_swing")
                for s in self.setups
            )
            if has_windowed_setups and not in_silver_bullet_window(now) and not in_judas_window(now):
                continue

            snap = snapshot_at(self.pre, now)
            recent_bars = bars.iloc[max(0, i - 1440) : i + 1]
            for setup in self.setups:
                sig = setup.evaluate(snap, now, recent_bars)
                if sig is None:
                    continue
                if (sig.setup, sig.side) in fired_today:
                    continue
                dec = self.risk.check(sig, account)
                if not dec.allow or dec.size_lots is None:
                    continue
                next_bar = bars.iloc[i + 1]
                entry = entry_fill(
                    sig.side,
                    Decimal(str(float(next_bar["open"]))),
                    self.symbol,
                )
                # Guard 1: fill must be on correct side of SL.
                # If entry >= sig.sl for SELL (or <= for BUY), SL is immediately crossed.
                if sig.side == Side.SELL and entry >= sig.sl:
                    continue
                if sig.side == Side.BUY and entry <= sig.sl:
                    continue
                # Guard 2: fill drift from zone midpoint capped at 5 pips.
                # Beyond that, ICT entry thesis (price at zone) is void.
                slip_pips = abs(entry - sig.entry) * Decimal("10000")
                if slip_pips > Decimal("5"):
                    continue
                # Guard 3: post-fill R:R must still pass 1.5.
                # Signal RR used zone midpoint; fill shifts entry, which can
                # invert R:R (TP closer than SL in actual terms).
                if sig.side == Side.SELL:
                    actual_risk = (sig.sl - entry) * Decimal("10000")
                    actual_reward = (entry - sig.tp) * Decimal("10000")
                else:
                    actual_risk = (entry - sig.sl) * Decimal("10000")
                    actual_reward = (sig.tp - entry) * Decimal("10000")
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
                    tp=sig.tp,
                    opened_at=next_bar["ts"].to_pydatetime(),
                    reason="open",
                )
                open_trades.append(opened)
                account = self.risk.on_fill(opened, account)
                fired_today.add((sig.setup, sig.side))
                next_ticket += 1
                break

        if prev_date is not None:
            equity_rows.append((pd.Timestamp(prev_date), account.equity))

        self.max_floating_dd_pct = max_floating_dd
        equity_df = pd.DataFrame(equity_rows, columns=["date", "equity"])
        return trades, equity_df
