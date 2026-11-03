from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pandas as pd
import numpy as np

from v17.common.types import Symbol, Side, TF
from v17.common.dtos import Zone, Signal, Trade
from v17.data.parquet_store import read_1m
from v17.config import get_settings
from v17.backtest.metrics import profit_factor
from v17.setups.sessions import in_silver_bullet_window, in_judas_window, window_id_for, asian_high_low
from v17.backtest.cost import pip_size, MIN_PIP_SL_BY_SYMBOL, PIP_SCALE
from v17.setups.targets import rr, passes_rr, pip_distance
from v17.data.resample import resample
from v17.structure.liquidity import detect_sweeps
from v17.structure.swings import detect_swings
from v17.structure.atr import atr
from v17.structure.bias import compute_bias_fast
from v17.risk.engine import DefaultRiskEngine
from v17.common.timeframes import tf_minutes

s = get_settings()
START = datetime(2018, 1, 1, tzinfo=UTC)
END = datetime(2018, 12, 31, 23, 59, tzinfo=UTC)

# 1. Correct ICT FVG Detection: Invalidation strictly on body close through the zone!
def detect_fvgs_correct(df_5m: pd.DataFrame) -> list[Zone]:
    out: list[Zone] = []
    df = df_5m.reset_index(drop=True)
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    ts = df["ts"].tolist()
    bar_dur = timedelta(minutes=5)
    n = len(df)
    
    for i in range(2, n):
        confirmed_at = ts[i].to_pydatetime() + bar_dur
        # Bullish FVG: low[i] > high[i-2]
        if lows[i] > highs[i - 2]:
            top = Decimal(str(lows[i]))
            bottom = Decimal(str(highs[i - 2]))
            top_f = float(top)
            bottom_f = float(bottom)
            
            # Invalidation: only when a candle body CLOSES below bottom!
            mit_at = None
            for j in range(i + 1, n):
                if closes[j] < bottom_f:
                    mit_at = ts[j].to_pydatetime()
                    break
                    
            out.append(Zone(
                kind="fvg",
                side=Side.BUY,
                tf=TF.M5,
                created_at=confirmed_at,
                top=top,
                bottom=bottom,
                mitigated_at=mit_at,
            ))
        # Bearish FVG: high[i] < low[i-2]
        elif highs[i] < lows[i - 2]:
            top = Decimal(str(lows[i - 2]))
            bottom = Decimal(str(highs[i]))
            top_f = float(top)
            bottom_f = float(bottom)
            
            # Invalidation: only when a candle body CLOSES above top!
            mit_at = None
            for j in range(i + 1, n):
                if closes[j] > top_f:
                    mit_at = ts[j].to_pydatetime()
                    break
                    
            out.append(Zone(
                kind="fvg",
                side=Side.SELL,
                tf=TF.M5,
                created_at=confirmed_at,
                top=top,
                bottom=bottom,
                mitigated_at=mit_at,
            ))
    return out

# Universal ICT Engine
symbols = [
    Symbol("EURUSD"),
    Symbol("GBPUSD"),
    Symbol("USDJPY"),
    Symbol("EURGBP"),
    Symbol("USATECHIDXUSD"),
]

symbol_results = []
all_trades = []

print("=== RUNNING UNIVERSAL ICT SETUP WITH CORRECT FVG MITIGATION (2018) ===")

for sym in symbols:
    df_1m = read_1m(sym, START, END, s.parquet_root)
    print(f"\nProcessing {sym} ({len(df_1m):,} bars)...")
    
    # Resample
    df_5m = resample(df_1m, TF.M5)
    df_15m = resample(df_1m, TF.M15)
    df_4h = resample(df_1m, TF.H4)
    df_1d = resample(df_1m, TF.D1)
    
    # Correct FVGs
    zones = detect_fvgs_correct(df_5m)
    zones.sort(key=lambda z: z.created_at)
    
    # Sweeps on 15m (swing_length=5)
    sweeps = detect_sweeps(df_15m, TF.M15, swing_length=5)
    sweeps.sort(key=lambda s: s.at)
    
    # Swings on 4H for bias
    swings_4h = detect_swings(df_4h, TF.H4, swing_length=3)
    swings_4h.sort(key=lambda s: s.at)
    
    # Daily EMA20
    ema20 = df_1d["close"].ewm(span=20, adjust=False).mean()
    
    # Pre-build daily bias map
    daily_bias_map = {}
    for d_idx in range(1, len(df_1d)):
        d_ts = df_1d["ts"].iloc[d_idx].to_pydatetime()
        day_date = d_ts.date()
        c_prev = Decimal(str(float(df_1d["close"].iloc[d_idx - 1])))
        ema_prev = Decimal(str(float(ema20.iloc[d_idx - 1])))
        # find last 4h swing before day_date
        s4 = [s for s in swings_4h if s.at.date() < day_date]
        last_4h_side = s4[-1].side if s4 else None
        b = compute_bias_fast(ema_prev, c_prev, last_4h_side)
        daily_bias_map[day_date] = b

    # Backtest Loop
    account = DefaultRiskEngine().ftmo
    starting_equity = Decimal("10000")
    
    from v17.backtest.loop import _fresh_account
    from v17.backtest.fills import entry_fill, exit_fill_on_bar, pnl_usd
    from v17.backtest.cost import commission
    
    acct = _fresh_account(starting_equity)
    trades = []
    open_trades = []
    peak_eq = starting_equity
    max_dd = 0.0
    fired_in_window = set()
    prev_date = None
    
    pip = pip_size(sym)
    min_sl = MIN_PIP_SL_BY_SYMBOL.get(sym, Decimal("3"))
    risk_engine = DefaultRiskEngine()
    
    opens = df_1m["open"].to_numpy()
    highs = df_1m["high"].to_numpy()
    lows = df_1m["low"].to_numpy()
    closes = df_1m["close"].to_numpy()
    ts_list = [t.to_pydatetime() for t in df_1m["ts"]]
    n_bars = len(df_1m)
    
    import bisect
    
    for i in range(n_bars - 1):
        now = ts_list[i]
        cur_date = now.date()
        
        # Mark to market
        if open_trades:
            low_dec = Decimal(str(float(lows[i])))
            high_dec = Decimal(str(float(highs[i])))
            bar_float = acct.equity
            for ot in open_trades:
                worst_px = low_dec if ot.side == Side.BUY else high_dec
                raw_float = pnl_usd(ot.side, ot.entry, worst_px, ot.size_lots, symbol=sym)
                comm_float = commission(ot.size_lots, sym)
                bar_float += (raw_float - comm_float)
            peak_eq = max(peak_eq, bar_float)
            if peak_eq > Decimal("0"):
                dd_val = float((peak_eq - bar_float) / peak_eq * Decimal("100"))
                max_dd = max(max_dd, dd_val)
                
            open_dec = Decimal(str(float(opens[i])))
            still_open = []
            for ot in open_trades:
                kind, exit_px = exit_fill_on_bar(ot.side, ot.sl, ot.tp, bar_open=open_dec, bar_high=high_dec, bar_low=low_dec)
                if kind != "none" and exit_px is not None:
                    raw_pnl = pnl_usd(ot.side, ot.entry, exit_px, ot.size_lots, symbol=sym)
                    comm = commission(ot.size_lots, sym)
                    closed = ot.model_copy(update={"closed_at": now, "close_price": exit_px, "pnl": raw_pnl - comm, "reason": kind})
                    trades.append(closed)
                    acct = risk_engine.on_close(closed, acct)
                else:
                    still_open.append(ot)
            open_trades = still_open
            
        if prev_date is not None and cur_date != prev_date:
            acct = acct.model_copy(update={"is_locked_today": False, "daily_realized_pnl": Decimal("0"), "trades_today": 0})
            fired_in_window = set()
        prev_date = cur_date
        
        if acct.kill_active or acct.is_locked_today:
            continue
            
        # Session check: Silver Bullet (London 03-04, NY AM 10-11, NY PM 14-15 NY)
        in_sb = in_silver_bullet_window(now)
        in_judas = in_judas_window(now)
        if not (in_sb or in_judas):
            continue
            
        bias = daily_bias_map.get(cur_date, Side.BUY)
        if hasattr(bias, "value") and bias.value == "none":
            continue
        side = Side.BUY if getattr(bias, "value", "bull") == "bull" else Side.SELL
        win_id = window_id_for(now)
        
        setup_name = "silver_bullet" if in_sb else "judas_swing"
        if (setup_name, side, win_id) in fired_in_window:
            continue
            
        # Recent liquidity sweep
        want_sweep = "ssl" if side == Side.BUY else "bsl"
        recent_sw = [s for s in sweeps if s.kind == want_sweep and (now - s.at) <= timedelta(minutes=60)]
        if not recent_sw:
            continue
        sweep_level = recent_sw[-1].level
        
        last_close = Decimal(str(float(closes[i])))
        
        # Find active FVG (must not be invalidated by close, and last_close is testing FVG)
        # Look back up to 2 hours for zones
        z_min_time = now - timedelta(hours=2)
        idx_left = bisect.bisect_left(zones, z_min_time, key=lambda z: z.created_at)
        idx_right = bisect.bisect_right(zones, now, key=lambda z: z.created_at)
        
        best_zone = None
        for z in zones[idx_left:idx_right]:
            if z.side != side:
                continue
            if z.mitigated_at is not None and z.mitigated_at <= now:
                continue
            # Price is inside or at threshold of FVG
            if (z.bottom - pip) <= last_close <= (z.top + pip):
                best_zone = z
                break
                
        if best_zone is None:
            continue
            
        entry = last_close
        if side == Side.BUY:
            sl = min(sweep_level, best_zone.bottom) - pip
            risk = entry - sl
            if risk <= 0:
                continue
            tp = entry + (risk * Decimal("2.0"))
        else:
            sl = max(sweep_level, best_zone.top) + pip
            risk = sl - entry
            if risk <= 0:
                continue
            tp = entry - (risk * Decimal("2.0"))
            
        if pip_distance(entry, sl, symbol=sym) < min_sl:
            continue
            
        rr_ = rr(entry, sl, tp, side)
        if not passes_rr(rr_, min_rr=Decimal("1.5")):
            continue
            
        from v17.common.types import SignalId, Ticket
        sig = Signal(
            id=SignalId(f"{sym}_{now.isoformat()}_{side.value}"),
            symbol=sym,
            setup=setup_name,
            side=side,
            at=now,
            entry=entry,
            sl=sl,
            tp=tp,
            rr=rr_,
            confluence={"bias": True, "fvg": True, "ob": False, "mss": True, "sweep": True},
        )
        dec = risk_engine.check(sig, acct)
        if not dec.allow or dec.size_lots is None:
            continue
            
        next_open = Decimal(str(float(opens[i + 1])))
        fill_entry = entry_fill(side, next_open, sym)
        if side == Side.SELL and fill_entry >= sl:
            continue
        if side == Side.BUY and fill_entry <= sl:
            continue
            
        actual_risk = (fill_entry - sl) if side == Side.BUY else (sl - fill_entry)
        if actual_risk <= Decimal("0"):
            continue
        adj_tp = fill_entry + (actual_risk * Decimal("2.0")) if side == Side.BUY else fill_entry - (actual_risk * Decimal("2.0"))
        
        filled = Trade(
            ticket=Ticket(len(trades) + len(open_trades) + 1),
            signal_id=sig.id,
            symbol=sym,
            side=side,
            size_lots=dec.size_lots,
            entry=fill_entry,
            sl=sl,
            tp=adj_tp,
            opened_at=now,
            reason="open",
        )
        acct = risk_engine.on_fill(filled, acct)
        open_trades.append(filled)
        fired_in_window.add((setup_name, side, win_id))
        
    pnls = [t.pnl for t in trades if t.pnl is not None]
    pf = profit_factor(pnls) if pnls else 0.0
    wins = sum(1 for p in pnls if p > 0)
    wr = (wins / len(pnls) * 100) if pnls else 0.0
    net_pnl = sum(pnls) if pnls else Decimal("0")
    
    symbol_results.append({
        "Symbol": str(sym),
        "Trades": len(trades),
        "Wins": wins,
        "Losses": len(trades) - wins,
        "WinRate%": round(wr, 1),
        "ProfitFactor": round(pf, 2),
        "MaxDD%": round(max_dd, 2),
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
print("=== 2018 UNIVERSAL PERFORMANCE ACROSS ALL 5 SYMBOLS ===")
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
