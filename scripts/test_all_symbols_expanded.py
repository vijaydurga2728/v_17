from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import pandas as pd

from v17.common.types import Symbol, Side
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.risk.engine import DefaultRiskEngine
from v17.setups.silver_bullet import SilverBullet
from v17.setups.judas_swing import JudasSwing
from v17.data.parquet_store import read_1m
from v17.config import get_settings
from v17.backtest.metrics import profit_factor
from v17.setups.sessions import window_id_for

s = get_settings()
START = datetime(2018, 1, 1, tzinfo=UTC)
END = datetime(2018, 12, 31, 23, 59, tzinfo=UTC)

symbols = [
    Symbol("EURUSD"),
    Symbol("GBPUSD"),
    Symbol("USDJPY"),
    Symbol("EURGBP"),
    Symbol("USATECHIDXUSD"),
]

# Modified EventLoop that uses window-level dedupe: (sig.setup, sig.side, window_id)
class WindowDedupeEventLoop(EventLoop):
    def run(self, start, end, starting_equity):
        bars = self.pre.bars_1m
        m = (bars["ts"] >= pd.Timestamp(start)) & (bars["ts"] <= pd.Timestamp(end))
        bars = bars[m].reset_index(drop=True)

        from v17.backtest.loop import _fresh_account
        from v17.common.types import Side
        from v17.backtest.cost import commission, PIP_SCALE, ZONE_TOLERANCE_BY_SYMBOL
        from v17.backtest.fills import exit_fill_on_bar, entry_fill, pnl_usd
        from v17.setups.sessions import in_silver_bullet_window, in_judas_window, window_id_for
        from v17.backtest.precompute import snapshot_at

        account = _fresh_account(starting_equity)
        trades = []
        equity_rows = []
        open_trades = []
        peak_floating_equity = starting_equity
        max_floating_dd = 0.0
        fired_in_window = set()
        prev_date = None

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

            if open_trades:
                low_dec = Decimal(str(float(lows[i])))
                high_dec = Decimal(str(float(highs[i])))
                bar_floating_equity = account.equity
                for ot in open_trades:
                    worst_px = low_dec if ot.side == Side.BUY else high_dec
                    raw_float = pnl_usd(ot.side, ot.entry, worst_px, ot.size_lots, symbol=self.symbol)
                    comm_float = commission(ot.size_lots, self.symbol)
                    bar_floating_equity += (raw_float - comm_float)

                peak_floating_equity = max(peak_floating_equity, bar_floating_equity)
                if peak_floating_equity > Decimal("0"):
                    dd_ratio = (peak_floating_equity - bar_floating_equity) / peak_floating_equity
                    dd = float(dd_ratio * Decimal("100"))
                    max_floating_dd = max(max_floating_dd, dd)

                open_dec = Decimal(str(float(opens[i])))
                still_open = []
                for ot in open_trades:
                    kind, exit_px = exit_fill_on_bar(ot.side, ot.sl, ot.tp, bar_open=open_dec, bar_high=high_dec, bar_low=low_dec)
                    if kind != "none" and exit_px is not None:
                        raw_pnl = pnl_usd(ot.side, ot.entry, exit_px, ot.size_lots, symbol=self.symbol)
                        comm = commission(ot.size_lots, self.symbol)
                        closed = ot.model_copy(update={"closed_at": now, "close_price": exit_px, "pnl": raw_pnl - comm, "reason": kind})
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
                fired_in_window = set()
                equity_rows.append((pd.Timestamp(prev_date), account.equity))
            prev_date = cur_date

            if account.kill_active or account.is_locked_today:
                continue

            in_window = in_silver_bullet_window(now) or in_judas_window(now)
            if not in_window:
                continue

            if self.calendar is not None and self.calendar.is_blackout(self.symbol, now, self.news_window_min):
                continue

            win_id = window_id_for(now)
            snap = snapshot_at(self.pre, now)
            recent_bars = bars.iloc[max(0, i - 1440) : i + 1]
            for setup in self.setups:
                sig = setup.evaluate(snap, now, recent_bars)
                if sig is None:
                    continue
                # Window-granular dedupe allows London SB and NY AM SB
                if (sig.setup, sig.side, win_id) in fired_in_window:
                    continue
                dec = self.risk.check(sig, account)
                if not dec.allow or dec.size_lots is None:
                    continue
                next_open = Decimal(str(float(opens[i + 1])))
                entry = entry_fill(sig.side, next_open, self.symbol)
                if sig.side == Side.SELL and entry >= sig.sl:
                    continue
                if sig.side == Side.BUY and entry <= sig.sl:
                    continue

                pip_scale_sym = Decimal(PIP_SCALE.get(self.symbol, 10000))
                slip_pips = abs(entry - sig.entry) * pip_scale_sym
                slip_cap = ZONE_TOLERANCE_BY_SYMBOL.get(self.symbol, Decimal("10"))
                if slip_pips > slip_cap:
                    continue

                tp_distance = abs(sig.tp - sig.entry)
                adj_tp = entry + tp_distance if sig.side == Side.BUY else entry - tp_distance
                if sig.side == Side.SELL:
                    actual_risk = (sig.sl - entry) * pip_scale_sym
                    actual_reward = (entry - adj_tp) * pip_scale_sym
                else:
                    actual_risk = (entry - sig.sl) * pip_scale_sym
                    actual_reward = (adj_tp - entry) * pip_scale_sym
                if actual_risk <= Decimal("0"):
                    continue
                if (actual_reward / actual_risk) < Decimal("1.5"):
                    continue

                from v17.common.dtos import Trade
                from v17.common.types import Ticket
                filled_trade = Trade(
                    ticket=Ticket(len(trades) + len(open_trades) + 1),
                    signal_id=sig.id,
                    symbol=self.symbol,
                    side=sig.side,
                    size_lots=dec.size_lots,
                    entry=entry,
                    sl=sig.sl,
                    tp=adj_tp,
                    opened_at=now,
                )
                account = self.risk.on_fill(filled_trade, account)
                open_trades.append(filled_trade)
                fired_in_window.add((sig.setup, sig.side, win_id))

        self.max_floating_dd_pct = max_floating_dd
        return trades, pd.DataFrame(equity_rows, columns=["date", "equity"])

symbol_results = []
all_trades = []

print("=== RUNNING EXPANDED SESSIONS ON ALL 5 SYMBOLS (2018) ===")

for sym in symbols:
    df = read_1m(sym, START, END, s.parquet_root)
    print(f"\nProcessing {sym} ({len(df):,} bars)...")
    pre = precompute(df, sym)
    setups = [JudasSwing(), SilverBullet()]
    loop = WindowDedupeEventLoop(sym, setups, DefaultRiskEngine(), pre)
    trades, equity = loop.run(START, END, Decimal("10000"))
    
    pnls = [t.pnl for t in trades if t.pnl is not None]
    pf = profit_factor(pnls) if pnls else 0.0
    wins = sum(1 for p in pnls if p > 0)
    wr = (wins / len(pnls) * 100) if pnls else 0.0
    dd = loop.max_floating_dd_pct
    net_pnl = sum(pnls) if pnls else Decimal("0")
    
    symbol_results.append({
        "Symbol": str(sym),
        "Trades": len(trades),
        "Wins": wins,
        "Losses": len(trades) - wins,
        "WinRate%": round(wr, 1),
        "ProfitFactor": round(pf, 2),
        "MaxDD%": round(dd, 2),
        "NetPnL": round(float(net_pnl), 2),
    })
    
    for t in trades:
        all_trades.append({
            "symbol": str(sym),
            "opened_at": t.opened_at,
            "closed_at": t.closed_at,
            "pnl": float(t.pnl) if t.pnl is not None else 0.0,
            "side": t.side.value,
            "reason": t.reason,
        })

res_df = pd.DataFrame(symbol_results)
print("\n" + "="*70)
print("=== 2018 ALL 5 SYMBOLS EXPANDED SESSION PERFORMANCE ===")
print("="*70)
print(res_df.to_string(index=False))

# --- FTMO 2-STEP EVALUATION ---
print("\n" + "="*70)
print("=== FTMO 2-STEP CHALLENGE AUDIT (ALL 5 SYMBOLS) ===")
print("="*70)

trades_chronological = sorted(all_trades, key=lambda x: x["closed_at"])
account_balance = 10000.0
peak_balance = 10000.0
max_overall_dd = 0.0

step1_passed = False
step1_date = None
step2_passed = False
step2_date = None

step1_start_bal = 10000.0
current_bal = step1_start_bal
step = 1
step1_trades = []
step2_trades = []

for tr in trades_chronological:
    current_bal += tr["pnl"]
    if current_bal > peak_balance:
        peak_balance = current_bal
    dd = (peak_balance - current_bal) / peak_balance * 100.0
    if dd > max_overall_dd:
        max_overall_dd = dd
        
    if step == 1:
        step1_trades.append(tr)
        if current_bal >= 11000.0:
            step1_passed = True
            step1_date = str(tr["closed_at"])[:10]
            step = 2
            current_bal = 10000.0
            peak_balance = 10000.0
    elif step == 2:
        step2_trades.append(tr)
        if current_bal >= 10500.0:
            step2_passed = True
            step2_date = str(tr["closed_at"])[:10]
            step = 3

print(f"Total Portfolio Trades in 2018: {len(trades_chronological)}")
total_net = sum(t["pnl"] for t in trades_chronological)
print(f"Total Portfolio Combined PnL: ${total_net:+.2f}")

print(f"\nStep 1 (10% Target = $1,000):")
print(f"  Passed: {'YES' if step1_passed else 'NO'}")
if step1_passed:
    print(f"  Passed on Date: {step1_date} (after {len(step1_trades)} trades)")
    
print(f"\nStep 2 (5% Target = $500):")
print(f"  Passed: {'YES' if step2_passed else 'NO'}")
if step2_passed:
    print(f"  Passed on Date: {step2_date} (after {len(step2_trades)} trades)")

print(f"\nFTMO Drawdown Guardrails:")
print(f"  Max Drawdown Observed: {max_overall_dd:.2f}% (Limit: < 10.0%)")
print(f"  Overall Compliance: {'PASS' if max_overall_dd < 10.0 else 'BREACHED'}")
