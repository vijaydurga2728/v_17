"""Path B: M1 Microstructure FVG Engine Prototype.

Detects M1 displacement and M1 FVG inside the Silver Bullet window,
conditioned on HTF Draw on Liquidity (DOL) and session liquidity sweeps.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from dataclasses import dataclass

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df, compute_metrics
from v17.setups import c22_silver_bullet as sb

cal_df = load_calendar_blackout_df()

print("Loading EURUSD...")
b_eur = sb.prepare(load_m1_symbol("EURUSD"))
print("Loading GBPUSD...")
b_gbp = sb.prepare(load_m1_symbol("GBPUSD"))

# M1 Fractal Pivots
print("Computing M1 fractal pivots...")
ph1_eur, pl1_eur = sb.pivot_flags(b_eur.mid_h, b_eur.mid_l, left=2, right=2)
ph1_gbp, pl1_gbp = sb.pivot_flags(b_gbp.mid_h, b_gbp.mid_l, left=2, right=2)

daily_df_eur = sb.build_daily_df(b_eur)
daily_df_gbp = sb.build_daily_df(b_gbp)

def find_m1_setup(
    b: sb.Bars,
    ph1: np.ndarray,
    pl1: np.ndarray,
    m1_start: int,
    m1_end: int,
    ctx: sb.DayContext,
    sp: sb.Spec,
    cur_spread: float,
) -> sb.Setup | None:
    """Scans for M1 microstructure displacement + FVG inside the window."""
    if ctx.dol_side == 0 or ctx.adr_exhausted:
        return None
    target_side = ctx.dol_side
    
    # Check if prior session/window price action swept liquidity
    # For long: did intraday price sweep Asian low or PDL or prior M1 swing low?
    # For short: did intraday price sweep Asian high or PDH or prior M1 swing high?
    
    for i2 in range(m1_start + 2, m1_end - 1):
        # 1. Displacement candle on M1
        rng2 = b.mid_h[i2] - b.mid_l[i2]
        if rng2 <= 0: continue
        body2 = abs(b.mid_c[i2] - b.mid_o[i2])
        if body2 / rng2 < sb.BODY_RATIO_MIN: continue
        if rng2 < sb.RANGE_ATR_MULT * b.atr[i2 - 1]: continue
        
        # 2. Market Structure Shift (MSS) on M1
        if target_side == 1:
            opp_idx = sb.latest_confirmed_pivot(ph1, i2, right=2)
            if opp_idx < 0 or opp_idx < m1_start - 30: continue
            if not (b.mid_c[i2] > b.mid_h[opp_idx]): continue
            # Find structural swing anchor
            anchor_px = float(np.min(b.mid_l[opp_idx:i2 + 1]))
        else:
            opp_idx = sb.latest_confirmed_pivot(pl1, i2, right=2)
            if opp_idx < 0 or opp_idx < m1_start - 30: continue
            if not (b.mid_c[i2] < b.mid_l[opp_idx]): continue
            # Find structural swing anchor
            anchor_px = float(np.max(b.mid_h[opp_idx:i2 + 1]))
            
        # 3. FVG on candle 3 (i3 = i2 + 1)
        i3 = i2 + 1
        if i3 >= len(b.mid_o): continue
        i1 = i2 - 1
        
        if target_side == 1:
            # Bullish FVG: low[i3] > high[i1]
            if not (b.mid_l[i3] > b.mid_h[i1]): continue
            entry_px = b.mid_h[i1]
            spread_buf = sb.SPREAD_BUFFER_MULT * cur_spread
            sl_px = anchor_px - spread_buf
            risk_dist = entry_px - sl_px
        else:
            # Bearish FVG: high[i3] < low[i1]
            if not (b.mid_h[i3] < b.mid_l[i1]): continue
            entry_px = b.mid_l[i1]
            spread_buf = sb.SPREAD_BUFFER_MULT * cur_spread
            sl_px = anchor_px + spread_buf
            risk_dist = sl_px - entry_px
            
        if risk_dist < sp.min_stop or risk_dist > sp.max_stop:
            continue
            
        tp_px = entry_px + target_side * (sb.MAX_TARGET_R * risk_dist)
        rr = abs(tp_px - entry_px) / risk_dist
        if rr < sb.MIN_RR:
            continue
            
        return sb.Setup(
            side=target_side,
            sweep_m5=0,
            anchor_px=anchor_px,
            c3_m5=0,
            c3_close_m1=i3,
            entry_px=entry_px,
            sl_px=sl_px,
            tp_px=tp_px,
            risk_dist=risk_dist,
            rr=rr,
        )
    return None

def run_m1_backtest(b, ph1, pl1, daily_df, sym, win, start_d, end_d):
    sp = sb.SPECS[sym]
    (sh, sm), (eh, em) = sb.WINDOWS[win]
    (end_h, end_m) = sb.SESSION_ENDS[win]
    days = pd.date_range(start_d, end_d, freq="B")
    trades = []
    
    for day in days:
        d = day.date()
        ctx = sb.compute_day_context(b, d, win, daily_df)
        if ctx is None or ctx.dol_side == 0 or ctx.adr_exhausted: continue
        
        d0_ns = pd.Timestamp(d).tz_localize("America/New_York").tz_convert("UTC").value
        ws_ns = d0_ns + (sh * 3600 + sm * 60) * 1_000_000_000
        we_ns = d0_ns + (eh * 3600 + em * 60) * 1_000_000_000
        sess_end_ns = d0_ns + (end_h * 3600 + end_m * 60) * 1_000_000_000
        
        m1_start = int(np.searchsorted(b.ts, ws_ns))
        m1_end = int(np.searchsorted(b.ts, we_ns))
        m1_sess_end = int(np.searchsorted(b.ts, sess_end_ns)) - 1
        if m1_end <= m1_start + 5 or m1_sess_end <= m1_end: continue
        
        cur_spread = float(b.ask_c[m1_start] - b.bid_c[m1_start]) if m1_start < len(b.ts) else 0.0001
        setup = find_m1_setup(b, ph1, pl1, m1_start, m1_end, ctx, sp, cur_spread)
        if setup is None: continue
        
        # M1 execution loop
        m1_start_fill = setup.c3_close_m1 + 1
        if m1_sess_end <= m1_start_fill: continue
        
        fill_i = -1
        for m in range(m1_start_fill, m1_sess_end):
            if setup.side == 1 and b.bid_l[m] <= setup.anchor_px: break
            if setup.side == -1 and b.ask_h[m] >= setup.anchor_px: break
            if setup.side == 1 and b.ask_l[m] <= setup.entry_px: fill_i = m; break
            if setup.side == -1 and b.bid_h[m] >= setup.entry_px: fill_i = m; break
            
        if fill_i < 0: continue
        
        exit_i, reason, exit_px = sb.execute_trade_m1(
            fill_i, m1_sess_end, setup.side, setup.sl_px, setup.tp_px,
            b.bid_o, b.bid_h, b.bid_l, b.bid_c, b.ask_o, b.ask_h, b.ask_l, b.ask_c,
        )
        r = sb.net_r(setup.side, setup.entry_px, exit_px, reason, setup.risk_dist, sp)
        trades.append({
            "day": d, "symbol": sym, "window": win, "side": setup.side,
            "entry_px": setup.entry_px, "sl_px": setup.sl_px, "tp_px": setup.tp_px,
            "r": r, "reason": reason, "fill_i": fill_i, "exit_i": exit_i,
        })
        
    return pd.DataFrame(trades)

print("\n--- Testing M1 Silver Bullet on EURUSD AM ---")
t_dev = run_m1_backtest(b_eur, ph1_eur, pl1_eur, daily_df_eur, "EURUSD", "AM", "2021-01-01", "2024-12-31")
t_oos = run_m1_backtest(b_eur, ph1_eur, pl1_eur, daily_df_eur, "EURUSD", "AM", "2025-01-01", "2026-12-31")
m_dev = compute_metrics(t_dev)
m_oos = compute_metrics(t_oos)
print(f"EURUSD AM DEV (2021-2024): n={m_dev['n']} | WR={m_dev['win_rate']*100:.1f}% | PF={m_dev['pf']:.2f} | MeanR={m_dev['mean_r']:+.3f}R")
print(f"EURUSD AM OOS (2025-2026): n={m_oos['n']} | WR={m_oos['win_rate']*100:.1f}% | PF={m_oos['pf']:.2f} | MeanR={m_oos['mean_r']:+.3f}R")

print("\n--- Testing M1 Silver Bullet on GBPUSD LDN ---")
sb.WINDOWS["LDN"] = ((3, 0), (4, 0))
sb.SESSION_ENDS["LDN"] = (8, 0)
sb.SPECS["GBPUSD"] = sb.Spec(min_stop=0.0015, max_stop=0.0035, slip=0.00005, commission_rt=0.00006)
t_dev_g = run_m1_backtest(b_gbp, ph1_gbp, pl1_gbp, daily_df_gbp, "GBPUSD", "LDN", "2021-01-01", "2024-12-31")
t_oos_g = run_m1_backtest(b_gbp, ph1_gbp, pl1_gbp, daily_df_gbp, "GBPUSD", "LDN", "2025-01-01", "2026-12-31")
m_dev_g = compute_metrics(t_dev_g)
m_oos_g = compute_metrics(t_oos_g)
print(f"GBPUSD LDN DEV (2021-2024): n={m_dev_g['n']} | WR={m_dev_g['win_rate']*100:.1f}% | PF={m_dev_g['pf']:.2f} | MeanR={m_dev_g['mean_r']:+.3f}R")
print(f"GBPUSD LDN OOS (2025-2026): n={m_oos_g['n']} | WR={m_oos_g['win_rate']*100:.1f}% | PF={m_oos_g['pf']:.2f} | MeanR={m_oos_g['mean_r']:+.3f}R")
