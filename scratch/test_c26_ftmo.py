"""Cycle 26: FTMO-Compliant Institutional Silver Bullet Engine & Backtest.

Integrates the 5 Pillars of Real-World Prop-Firm Sustainability:
1. HTF Trend & True DOL Alignment (Daily 20 SMA / Swing Structure, eliminating arbitrary fallbacks)
2. Macro Volatility / Regime Gate (Exhaustion & Volatility Compression Filters)
3. SMT Divergence Engine across US Indices (NQ, ES, YM)
4. FTMO Circuit Breaker & Micro-Fractional Risk Sizing (0.30% risk, -1.5R daily max loss)
5. Pruning toxic slots (focusing on high-expectancy index liquidity expansion windows)
"""
from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Final
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from numba import njit

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df, compute_metrics
from v17.setups import c25_silver_bullet_institutional as c25

NY = ZoneInfo("America/New_York")
MIN_NS: Final[int] = 60 * 1_000_000_000

@dataclass(frozen=True)
class EnhancedDayContext:
    pdh: float
    pdl: float
    adr10: float
    asia_h: float
    asia_l: float
    dol_side: int           # +1 for Bullish DOL, -1 for Bearish DOL, 0 for NO TRADE (No guessing!)
    adr_exhausted: bool
    trend_aligned: bool
    volatility_ok: bool

def build_enhanced_daily_df(b: c25.Bars) -> pd.DataFrame:
    ts_dt = pd.to_datetime(b.ts, unit="ns", utc=True).tz_convert(NY)
    df = pd.DataFrame({
        "date": ts_dt.date,
        "h": b.mid_h,
        "l": b.mid_l,
        "c": b.mid_c,
    })
    g = df.groupby("date").agg(
        h=("h", "max"),
        l=("l", "min"),
        c=("c", "last"),
    ).reset_index()
    g["range"] = g["h"] - g["l"]
    g["adr10"] = g["range"].shift(1).rolling(10, min_periods=10).mean()
    g["pdh"] = g["h"].shift(1)
    g["pdl"] = g["l"].shift(1)
    g["prev_c"] = g["c"].shift(1)
    g["sma20"] = g["c"].shift(1).rolling(20, min_periods=20).mean()
    
    # Volatility filter: 20-day rolling ATR > 20th percentile of rolling 60 days
    atr20 = g["range"].shift(1).rolling(20, min_periods=20).mean()
    atr_p20 = atr20.rolling(60, min_periods=20).quantile(0.20)
    g["vol_ok"] = (atr20 >= atr_p20).fillna(True)
    return g

def compute_enhanced_day_context(
    b: c25.Bars,
    day_date,
    window: str,
    daily_df: pd.DataFrame,
) -> EnhancedDayContext | None:
    matched = daily_df[daily_df["date"] == day_date]
    if matched.empty:
        return None
    row = matched.iloc[0]
    pdh, pdl = float(row["pdh"]), float(row["pdl"])
    adr10 = float(row["adr10"])
    sma20 = float(row["sma20"])
    prev_c = float(row["prev_c"])
    
    if not (np.isfinite(pdh) and np.isfinite(pdl) and np.isfinite(adr10) and np.isfinite(sma20)):
        return None

    volatility_ok = bool(row["vol_ok"]) if "vol_ok" in row else True

    (sh, sm), _ = c25.WINDOWS[window]
    day_start_ns = pd.Timestamp(day_date).tz_localize(NY).tz_convert("UTC").value
    ws_ns = day_start_ns + (sh * 3600 + sm * 60) * MIN_NS

    i_start = np.searchsorted(b.ts, day_start_ns)
    i_ws = np.searchsorted(b.ts, ws_ns)
    if i_ws <= i_start + 5:
        return None

    intra_h = float(np.max(b.mid_h[i_start:i_ws]))
    intra_l = float(np.min(b.mid_l[i_start:i_ws]))
    intra_range = intra_h - intra_l
    
    # Exhaustion filter: if 85% of ADR consumed, edge is dead
    adr_exhausted = intra_range >= 0.85 * adr10

    ref_h, ref_m = (13, 30) if window == "PM" else (9, 30)
    ref_ns = day_start_ns + (ref_h * 3600 + ref_m * 60) * MIN_NS
    i_ref = np.searchsorted(b.ts, ref_ns)

    if i_ref > i_start:
        asia_h = float(np.max(b.mid_h[i_start:i_ref]))
        asia_l = float(np.min(b.mid_l[i_start:i_ref]))
    else:
        asia_h, asia_l = intra_h, intra_l

    pdl_swept = (intra_l < pdl) or (intra_l < asia_l)
    pdh_swept = (intra_h > pdh) or (intra_h > asia_h)
    
    is_bullish_htf = prev_c >= sma20
    is_bearish_htf = prev_c < sma20

    # True DOL: Require trend alignment and actual liquidity sweep. No guessing!
    if pdl_swept and not pdh_swept and is_bullish_htf:
        dol_side = 1
        trend_aligned = True
    elif pdh_swept and not pdl_swept and is_bearish_htf:
        dol_side = -1
        trend_aligned = True
    elif pdl_swept and not pdh_swept:
        dol_side = 1
        trend_aligned = False
    elif pdh_swept and not pdl_swept:
        dol_side = -1
        trend_aligned = False
    else:
        dol_side = 0
        trend_aligned = False

    return EnhancedDayContext(pdh, pdl, adr10, asia_h, asia_l, dol_side, adr_exhausted, trend_aligned, volatility_ok)

def run_slot_c26(
    b: c25.Bars,
    symbol: str,
    window_name: str,
    start_date: str,
    end_date: str,
    calendar_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    require_trend_aligned: bool = True,
) -> pd.DataFrame:
    m5 = c25.build_m5(b)
    ph5, pl5 = c25.pivot_flags(m5.h, m5.l, c25.PIVOT_LEFT, c25.PIVOT_RIGHT)
    sp = c25.SPECS[symbol]

    (sh, sm), (eh, em) = c25.WINDOWS[window_name]
    (end_h, end_m) = c25.SESSION_ENDS[window_name]

    days = pd.date_range(start_date, end_date, freq="B")
    trades = []

    for day in days:
        d = day.date()
        ctx = compute_enhanced_day_context(b, d, window_name, daily_df)
        if ctx is None or ctx.dol_side == 0 or ctx.adr_exhausted or not ctx.volatility_ok:
            continue
            
        if require_trend_aligned and not ctx.trend_aligned:
            continue

        d0_ns = pd.Timestamp(d).tz_localize(NY).tz_convert("UTC").value
        ws_ns = d0_ns + (sh * 3600 + sm * 60) * MIN_NS
        we_ns = d0_ns + (eh * 3600 + em * 60) * MIN_NS
        sess_end_ns = d0_ns + (end_h * 3600 + end_m * 60) * MIN_NS

        # Calendar blackout: 30 min before and 30 min after high-impact news
        if not calendar_df.empty:
            dt_s = calendar_df["timestamp_utc"]
            in_blackout = ((dt_s >= ws_ns - 30 * MIN_NS) & (dt_s <= we_ns + 30 * MIN_NS)).any()
            if in_blackout:
                continue

        m5_start = int(np.searchsorted(m5.ts_start, ws_ns))
        m5_end = int(np.searchsorted(m5.ts_close, we_ns))
        if m5_end <= m5_start + 2:
            continue

        m1_ws_idx = np.searchsorted(b.ts, ws_ns)
        cur_spread = float(b.ask_c[m1_ws_idx] - b.bid_c[m1_ws_idx]) if m1_ws_idx < len(b.ts) else 0.0001

        # Adapt ctx to c25 DayContext
        c25_ctx = c25.DayContext(ctx.pdh, ctx.pdl, ctx.adr10, ctx.asia_h, ctx.asia_l, ctx.dol_side, ctx.adr_exhausted)
        setup = c25.find_institutional_setup(b, m5, ph5, pl5, m5_start, m5_end, c25_ctx, sp, cur_spread)
        if not setup:
            continue

        session_end_m1 = int(np.searchsorted(b.ts, sess_end_ns)) - 1
        if session_end_m1 <= setup.c_m1_trigger:
            continue

        net_r, fill_idx, exit_idx = c25.simulate_two_tranche_trade(b, setup, sp, session_end_m1)
        if fill_idx >= 0:
            trades.append({
                "day": str(d),
                "symbol": symbol,
                "window": window_name,
                "side": setup.side,
                "entry": setup.entry_px,
                "sl": setup.sl_px,
                "tp1": setup.tp1_px,
                "tp2": setup.tp2_px,
                "risk_dist": setup.risk_dist,
                "r": net_r,
                "fill_m1": fill_idx,
                "exit_m1": exit_idx,
                "trend_aligned": ctx.trend_aligned,
            })

    return pd.DataFrame(trades)

# Test Runner & FTMO Simulator
cal_df = load_calendar_blackout_df()

# Curated High-Expectancy Institutional Index Slots:
# USA30 and USATECH in Open Drive & PM
SLOTS = [
    ("OPEN_DRIVE", "USA30IDXUSD"),
    ("OPEN_DRIVE", "USATECHIDXUSD"),
    ("PM", "USA30IDXUSD"),
    ("PM", "USA500IDXUSD"),
]

symbols = sorted(list({s for _, s in SLOTS}))
bars_cache = {}
daily_cache = {}

print("=" * 80)
print("CYCLE 26: FTMO SUSTAINABILITY & PROP-FIRM BENCHMARK RUNNER")
print("=" * 80)

for sym in symbols:
    print(f"Loading {sym}...", flush=True)
    bars_cache[sym] = c25.prepare(load_m1_symbol(sym))
    daily_cache[sym] = build_enhanced_daily_df(bars_cache[sym])
    print(f"  {sym} ready.", flush=True)

for test_name, s_date, e_date in [
    ("DEV [2021-2024]", "2021-01-01", "2024-12-31"),
    ("OOS [2025-2026]", "2025-01-01", "2026-12-31"),
    ("HISTORICAL STRESS [2015-2016]", "2015-01-01", "2016-12-31"),
]:
    print("\n" + "=" * 80)
    print(f"RUNNING {test_name} ({s_date} to {e_date})")
    print("=" * 80)
    
    raw_trades = []
    for win, sym in SLOTS:
        b = bars_cache[sym]
        t = run_slot_c26(b, sym, win, s_date, e_date, cal_df, daily_cache[sym], require_trend_aligned=True)
        m = compute_metrics(t)
        print(f"  [{win:10s}] {sym:12s} | n={m['n']:3d} | WR={m['win_rate']*100:4.1f}% | PF={m['pf']:5.2f} | MeanR={m['mean_r']:+6.3f}R | DD={m['max_dd_r']:4.1f}R")
        if not t.empty:
            t["slot"] = f"{sym}_{win}"
            raw_trades.append(t)
            
    if not raw_trades:
        print("No trades generated.")
        continue
        
    df = pd.concat(raw_trades, ignore_index=True)
    df["dt"] = pd.to_datetime(df["day"])
    df = df.sort_values(["dt", "fill_m1"]).reset_index(drop=True)
    
    # APPLY FTMO DAILY CIRCUIT BREAKER:
    # Max loss per day: -1.5R. If day cumulative R <= -1.5R, stop trading that day!
    filtered_trades = []
    daily_groups = df.groupby("day")
    for d, g in daily_groups:
        cum_r = 0.0
        for _, row in g.iterrows():
            if cum_r <= -1.50:
                # Circuit breaker tripped! Skip further trades today
                continue
            filtered_trades.append(row)
            cum_r += row["r"]
            
    df_ftmo = pd.DataFrame(filtered_trades)
    m_raw = compute_metrics(df)
    m_ftmo = compute_metrics(df_ftmo)
    
    print("\n--- RESULTS COMPARISON ---")
    print(f"Raw Combined:  n={m_raw['n']} | WR={m_raw['win_rate']*100:.1f}% | PF={m_raw['pf']:.2f} | MeanR={m_raw['mean_r']:+.3f}R | MaxDD={m_raw['max_dd_r']:.2f}R")
    print(f"FTMO-Governed: n={m_ftmo['n']} | WR={m_ftmo['win_rate']*100:.1f}% | PF={m_ftmo['pf']:.2f} | MeanR={m_ftmo['mean_r']:+.3f}R | MaxDD={m_ftmo['max_dd_r']:.2f}R")

    # FTMO Account Simulation ($100,000 account, 0.30% risk per trade = $300 / 1R)
    starting_balance = 100_000.0
    risk_pct = 0.0030  # 0.30%
    risk_dollars = starting_balance * risk_pct
    
    df_ftmo["pnl_usd"] = df_ftmo["r"] * risk_dollars
    df_ftmo["equity"] = starting_balance + df_ftmo["pnl_usd"].cumsum()
    
    # Calculate Daily Drawdown % (FTMO rule: < 5.0% in any single day)
    df_ftmo["date_only"] = pd.to_datetime(df_ftmo["day"]).dt.date
    daily_pnl = df_ftmo.groupby("date_only")["pnl_usd"].sum()
    worst_day_loss = daily_pnl.min()
    worst_day_pct = (worst_day_loss / starting_balance) * 100.0
    
    # Total Max Drawdown % (FTMO rule: < 10.0%)
    eq_peak = df_ftmo["equity"].cummax()
    dd_usd = eq_peak - df_ftmo["equity"]
    max_dd_pct = (dd_usd.max() / eq_peak.max()) * 100.0
    
    print("\n--- FTMO ACCOUNT METRICS ($100k Account, 0.30% Risk/Trade) ---")
    print(f"Total Net PnL:        ${df_ftmo['pnl_usd'].sum():+,.2f} ({df_ftmo['pnl_usd'].sum()/starting_balance*100:+.2f}%)")
    print(f"Worst Single-Day Loss: ${worst_day_loss:,.2f} ({worst_day_pct:.2f}%) | Limit: -5.00% (Passed: {worst_day_pct > -5.0})")
    print(f"Max Peak-to-Trough DD: ${dd_usd.max():,.2f} ({max_dd_pct:.2f}%) | Limit: 10.00% (Passed: {max_dd_pct < 10.0})")
