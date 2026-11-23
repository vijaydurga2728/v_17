"""Test M5 Sweep + M5 MSS + M1 FVG Execution.

Retains institutional M5 market structure (preserving the 1.83 PF edge),
while scanning M1 bars within the M5 displacement candle to find valid M1 FVGs.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df, compute_metrics
from v17.setups import c22_silver_bullet as sb

cal_df = load_calendar_blackout_df()

print("Loading EURUSD...")
b_eur = sb.prepare(load_m1_symbol("EURUSD"))
m5_eur = sb.build_m5(b_eur)
ph5_eur, pl5_eur = sb.pivot_flags(m5_eur.h, m5_eur.l, 2, 2)
daily_df_eur = sb.build_daily_df(b_eur)
sp_eur = sb.SPECS["EURUSD"]

print("Loading GBPUSD...")
b_gbp = sb.prepare(load_m1_symbol("GBPUSD"))
m5_gbp = sb.build_m5(b_gbp)
ph5_gbp, pl5_gbp = sb.pivot_flags(m5_gbp.h, m5_gbp.l, 2, 2)
daily_df_gbp = sb.build_daily_df(b_gbp)
sp_gbp = sb.Spec(min_stop=0.0015, max_stop=0.0035, slip=0.00005, commission_rt=0.00006)

def find_m5_mss_m1_fvg_setup(
    b: sb.Bars,
    m5: sb.M5Bars,
    ph5: np.ndarray,
    pl5: np.ndarray,
    m5_start: int,
    m5_end: int,
    ctx: sb.DayContext,
    sp: sb.Spec,
    cur_spread: float,
) -> list[sb.Setup]:
    """Finds setups where M5 sweeps + M5 breaks structure, and M1 provides the FVG."""
    if ctx.dol_side == 0 or ctx.adr_exhausted:
        return []
    target_side = ctx.dol_side
    setups = []
    
    for k in range(m5_start, m5_end):
        if not np.isfinite(m5.atr[k]) or m5.atr[k] <= 0: continue
        
        # 1. M5 Sweep
        if target_side == 1:
            p_idx = sb.latest_confirmed_pivot(pl5, k, right=2)
            if p_idx < 0 or not (m5.l[k] < m5.l[p_idx]): continue
            anchor_px = m5.l[k]
        else:
            p_idx = sb.latest_confirmed_pivot(ph5, k, right=2)
            if p_idx < 0 or not (m5.h[k] > m5.h[p_idx]): continue
            anchor_px = m5.h[k]
            
        # 2. M5 Displacement + MSS
        for k2 in range(k + 1, min(k + 6, m5_end)):
            rng2 = m5.h[k2] - m5.l[k2]
            if rng2 <= 0: continue
            if abs(m5.c[k2] - m5.o[k2]) / rng2 < sb.BODY_RATIO_MIN: continue
            if rng2 < sb.RANGE_ATR_MULT * m5.atr[k2 - 1]: continue
            
            if target_side == 1:
                opp_idx = sb.latest_confirmed_pivot(ph5, k2, right=2)
                if opp_idx < 0 or opp_idx < p_idx or not (m5.c[k2] > m5.h[opp_idx]): continue
                anchor_px = min(anchor_px, float(np.min(m5.l[k:k2 + 1])))
            else:
                opp_idx = sb.latest_confirmed_pivot(pl5, k2, right=2)
                if opp_idx < 0 or opp_idx < p_idx or not (m5.c[k2] < m5.l[opp_idx]): continue
                anchor_px = max(anchor_px, float(np.max(m5.h[k:k2 + 1])))
                
            # 3. Find M1 FVGs inside or immediately after the displacement candle k2
            m1_k2_start = int(m5.m1_end_idx[k2 - 1]) if k2 > 0 else 0
            m1_k2_end = int(m5.m1_end_idx[k2]) + 5 # allow up to 5 mins after MSS
            if m1_k2_end >= len(b.mid_o): m1_k2_end = len(b.mid_o) - 1
            
            for m in range(m1_k2_start + 2, m1_k2_end):
                m1 = m - 1
                m3 = m + 1
                if m3 >= len(b.mid_o): break
                
                if target_side == 1:
                    # M1 Bullish FVG: low[m3] > high[m1]
                    if not (b.mid_l[m3] > b.mid_h[m1]): continue
                    entry_px = b.mid_h[m1]
                    sl_px = anchor_px - sb.SPREAD_BUFFER_MULT * cur_spread
                    risk_dist = entry_px - sl_px
                else:
                    # M1 Bearish FVG: high[m3] < low[m1]
                    if not (b.mid_h[m3] < b.mid_l[m1]): continue
                    entry_px = b.mid_l[m1]
                    sl_px = anchor_px + sb.SPREAD_BUFFER_MULT * cur_spread
                    risk_dist = sl_px - entry_px
                    
                if risk_dist < sp.min_stop or risk_dist > sp.max_stop: continue
                tp_px = entry_px + target_side * (sb.MAX_TARGET_R * risk_dist)
                rr = abs(tp_px - entry_px) / risk_dist
                if rr < sb.MIN_RR: continue
                
                setups.append(sb.Setup(
                    side=target_side, sweep_m5=k, anchor_px=anchor_px,
                    c3_m5=k2, c3_close_m1=m3, entry_px=entry_px,
                    sl_px=sl_px, tp_px=tp_px, risk_dist=risk_dist, rr=rr,
                ))
                break # 1 setup per displacement
            if setups: break
        if setups: break
    return setups

def run_hybrid_backtest(b, m5, ph5, pl5, daily_df, sym, win, sp, start_d, end_d):
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
        
        m5_start = int(np.searchsorted(m5.ts_start, ws_ns))
        m5_end = int(np.searchsorted(m5.ts_close, we_ns))
        if m5_end <= m5_start + 2: continue
        
        m1_start = int(np.searchsorted(b.ts, ws_ns))
        m1_sess_end = int(np.searchsorted(b.ts, sess_end_ns)) - 1
        if m1_sess_end <= m1_start + 10: continue
        
        cur_spread = float(b.ask_c[m1_start] - b.bid_c[m1_start]) if m1_start < len(b.ts) else 0.0001
        setups = find_m5_mss_m1_fvg_setup(b, m5, ph5, pl5, m5_start, m5_end, ctx, sp, cur_spread)
        if not setups: continue
        
        for setup in setups:
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
            break # 1 trade per day
            
    return pd.DataFrame(trades)

print("\n--- Hybrid M5-MSS + M1-FVG on EURUSD AM ---")
t_eur_dev = run_hybrid_backtest(b_eur, m5_eur, ph5_eur, pl5_eur, daily_df_eur, "EURUSD", "AM", sp_eur, "2021-01-01", "2024-12-31")
t_eur_oos = run_hybrid_backtest(b_eur, m5_eur, ph5_eur, pl5_eur, daily_df_eur, "EURUSD", "AM", sp_eur, "2025-01-01", "2026-12-31")
m_ed = compute_metrics(t_eur_dev)
m_eo = compute_metrics(t_eur_oos)
print(f"EURUSD AM DEV: n={m_ed['n']} | WR={m_ed['win_rate']*100:.1f}% | PF={m_ed['pf']:.2f} | MeanR={m_ed['mean_r']:+.3f}R")
print(f"EURUSD AM OOS: n={m_eo['n']} | WR={m_eo['win_rate']*100:.1f}% | PF={m_eo['pf']:.2f} | MeanR={m_eo['mean_r']:+.3f}R")

print("\n--- Hybrid M5-MSS + M1-FVG on GBPUSD LDN ---")
sb.WINDOWS["LDN"] = ((3, 0), (4, 0))
sb.SESSION_ENDS["LDN"] = (8, 0)
t_gbp_dev = run_hybrid_backtest(b_gbp, m5_gbp, ph5_gbp, pl5_gbp, daily_df_gbp, "GBPUSD", "LDN", sp_gbp, "2021-01-01", "2024-12-31")
t_gbp_oos = run_hybrid_backtest(b_gbp, m5_gbp, ph5_gbp, pl5_gbp, daily_df_gbp, "GBPUSD", "LDN", sp_gbp, "2025-01-01", "2026-12-31")
m_gd = compute_metrics(t_gbp_dev)
m_go = compute_metrics(t_gbp_oos)
print(f"GBPUSD LDN DEV: n={m_gd['n']} | WR={m_gd['win_rate']*100:.1f}% | PF={m_gd['pf']:.2f} | MeanR={m_gd['mean_r']:+.3f}R")
print(f"GBPUSD LDN OOS: n={m_go['n']} | WR={m_go['win_rate']*100:.1f}% | PF={m_go['pf']:.2f} | MeanR={m_go['mean_r']:+.3f}R")
