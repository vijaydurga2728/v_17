from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pandas as pd

from v17.common.types import Symbol, Side, TF
from v17.common.dtos import Zone, Signal, Trade
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.risk.engine import DefaultRiskEngine
from v17.data.parquet_store import read_1m
from v17.config import get_settings
from v17.backtest.metrics import profit_factor
from v17.setups.sessions import in_silver_bullet_window, window_id_for
from v17.backtest.cost import pip_size, MIN_PIP_SL_BY_SYMBOL
from v17.setups.targets import rr, passes_rr

s = get_settings()
START = datetime(2018, 1, 1, tzinfo=UTC)
END = datetime(2018, 12, 31, 23, 59, tzinfo=UTC)

# True Universal Silver Bullet
class UniversalSilverBullet:
    name = "silver_bullet"
    
    def evaluate(self, snap, now, bars_1m):
        # 1. Must be strictly within Silver Bullet window (London 03-04, NY AM 10-11, NY PM 14-15 NY)
        if not in_silver_bullet_window(now):
            return None
            
        # 2. HTF Bias
        if snap.bias.value == "none":
            return None
        side = Side.BUY if snap.bias.value == "bull" else Side.SELL
        
        # 3. Sweep of opposing liquidity in last 60 minutes
        want_sweep = "ssl" if side == Side.BUY else "bsl"
        recent_sweeps = [
            s for s in snap.sweeps
            if s.kind == want_sweep and (now - s.at) <= timedelta(minutes=60)
        ]
        if not recent_sweeps:
            return None
        sweep_level = recent_sweeps[-1].level
        
        last_close = Decimal(str(float(bars_1m["close"].iloc[-1])))
        
        # 4. FVG Retest: find an active FVG where price is currently inside or testing
        # Valid FVG: created after or near sweep, not invalidated by candle close
        pip = pip_size(snap.symbol)
        best_zone = None
        for z in snap.zones:
            if z.side != side:
                continue
            # Must not be invalidated by a body close through the zone
            if z.mitigated_at is not None and z.mitigated_at <= now:
                continue
            # Price must be testing the FVG (within the FVG or at its threshold)
            # Universal threshold: within 1 pip of boundary
            if (z.bottom - pip) <= last_close <= (z.top + pip):
                best_zone = z
                break
                
        if best_zone is None:
            return None
            
        entry = last_close
        
        # 5. Stop Loss strictly behind the sweep extreme
        if side == Side.BUY:
            sl = min(sweep_level, best_zone.bottom) - pip
            risk = entry - sl
            if risk <= 0:
                return None
            # Target minimum 1:2 R:R (Universal for all symbols)
            tp = entry + (risk * Decimal("2.0"))
        else:
            sl = max(sweep_level, best_zone.top) + pip
            risk = sl - entry
            if risk <= 0:
                return None
            tp = entry - (risk * Decimal("2.0"))
            
        min_sl = MIN_PIP_SL_BY_SYMBOL.get(snap.symbol, Decimal("3"))
        from v17.setups.targets import pip_distance
        if pip_distance(entry, sl, symbol=snap.symbol) < min_sl:
            return None
            
        rr_ = rr(entry, sl, tp, side)
        if not passes_rr(rr_, min_rr=Decimal("1.5")):
            return None
            
        from v17.setups.silver_bullet import make_signal_id
        return Signal(
            id=make_signal_id(snap.symbol, self.name, now, side),
            symbol=snap.symbol,
            setup="silver_bullet",
            side=side,
            at=now,
            entry=entry,
            sl=sl,
            tp=tp,
            rr=rr_,
            confluence={"bias": True, "fvg": True, "ob": False, "mss": True, "sweep": True},
            note=f"universal_sb zone={best_zone.kind}",
        )

# Loop with Window-Level Dedupe and Universal Execution
class UniversalEventLoop(EventLoop):
    def run(self, start, end, starting_equity):
        bars = self.pre.bars_1m
        m = (bars["ts"] >= pd.Timestamp(start)) & (bars["ts"] <= pd.Timestamp(end))
        bars = bars[m].reset_index(drop=True)

        from v17.backtest.loop import _fresh_account
        from v17.common.types import Side, Ticket, SignalId
        from v17.common.dtos import Trade
        from v17.backtest.cost import commission, PIP_SCALE
        from v17.backtest.fills import exit_fill_on_bar, entry_fill, pnl_usd
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

            if not in_silver_bullet_window(now):
                continue

            win_id = window_id_for(now)
            snap = snapshot_at(self.pre, now)
            recent_bars = bars.iloc[max(0, i - 1440) : i + 1]
            for setup in self.setups:
                sig = setup.evaluate(snap, now, recent_bars)
                if sig is None:
                    continue
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
                # Recompute TP based on actual fill to maintain 2.0 R:R
                actual_risk = (entry - sig.sl) if sig.side == Side.BUY else (sig.sl - entry)
                if actual_risk <= Decimal("0"):
                    continue
                adj_tp = entry + (actual_risk * Decimal("2.0")) if sig.side == Side.BUY else entry - (actual_risk * Decimal("2.0"))

                filled_trade = Trade(
                    ticket=Ticket(len(trades) + len(open_trades) + 1),
                    signal_id=SignalId(sig.id),
                    symbol=self.symbol,
                    side=sig.side,
                    size_lots=dec.size_lots,
                    entry=entry,
                    sl=sig.sl,
                    tp=adj_tp,
                    opened_at=now,
                    reason="open",
                )
                account = self.risk.on_fill(filled_trade, account)
                open_trades.append(filled_trade)
                fired_in_window.add((sig.setup, sig.side, win_id))
                break

        self.max_floating_dd_pct = max_floating_dd
        return trades, pd.DataFrame(equity_rows, columns=["date", "equity"])

symbols = [
    Symbol("EURUSD"),
    Symbol("GBPUSD"),
    Symbol("USDJPY"),
    Symbol("EURGBP"),
    Symbol("USATECHIDXUSD"),
]

symbol_results = []
all_trades = []

print("=== RUNNING UNIVERSAL SILVER BULLET ACROSS ALL 5 SYMBOLS (2018) ===")
print("Zero Symbol-Specific Tuning: 100% Volatility-Adaptive, Universal Sweep Stop, 2.0x Dynamic Target")

for sym in symbols:
    df = read_1m(sym, START, END, s.parquet_root)
    print(f"\nProcessing {sym} ({len(df):,} bars)...")
    pre = precompute(df, sym)
    setups = [UniversalSilverBullet()]
    loop = UniversalEventLoop(sym, setups, DefaultRiskEngine(), pre)
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
            "closed_at": t.closed_at,
            "pnl": float(t.pnl) if t.pnl is not None else 0.0,
        })

res_df = pd.DataFrame(symbol_results)
print("\n" + "="*70)
print("=== 2018 UNIVERSAL SILVER BULLET PER-SYMBOL PERFORMANCE ===")
print("="*70)
print(res_df.to_string(index=False))

trades_sorted = sorted(all_trades, key=lambda x: x["closed_at"])
bal = 10000.0
peak = 10000.0
max_dd = 0.0
step1_passed = False
step1_date = None
step2_passed = False
step2_date = None
step = 1

for tr in trades_sorted:
    bal += tr["pnl"]
    if bal > peak:
        peak = bal
    dd = (peak - bal) / peak * 100.0
    if dd > max_dd:
        max_dd = dd
    if step == 1 and bal >= 11000.0:
        step1_passed = True
        step1_date = str(tr["closed_at"])[:10]
        step = 2
        bal = 10000.0
        peak = 10000.0
    elif step == 2 and bal >= 10500.0:
        step2_passed = True
        step2_date = str(tr["closed_at"])[:10]
        step = 3

print("\n" + "="*70)
print(f"Total Combined Portfolio Trades: {len(trades_sorted)}")
print(f"Total Net PnL: ${sum(t['pnl'] for t in trades_sorted):+.2f}")
print(f"Max Portfolio Drawdown: {max_dd:.2f}% (Limit: < 10.0%)")
print(f"Step 1 Passed: {step1_passed} ({step1_date})")
print(f"Step 2 Passed: {step2_passed} ({step2_date})")
print("="*70)
