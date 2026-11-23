"""Diagnose the exact funnel dropping trade signals in Cycle 22 Silver Bullet.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df
from v17.setups import c22_silver_bullet as sb

cal_df = load_calendar_blackout_df()
b_eur = sb.prepare(load_m1_symbol("EURUSD"))
m5 = sb.build_m5(b_eur)
ph5, pl5 = sb.pivot_flags(m5.h, m5.l, left=2, right=2)
daily_df = sb.build_daily_df(b_eur)
sp = sb.SPECS["EURUSD"]

window = "AM"
sh, sm = sb.WINDOWS[window][0]
eh, em = sb.WINDOWS[window][1]

funnel = {
    "total_days": 0,
    "has_daily_ctx": 0,
    "dol_non_zero": 0,
    "adr_not_exhausted": 0,
    "sweep_found": 0,
    "disp_found": 0,
    "mss_found": 0,
    "fvg_found": 0,
    "stop_in_bounds": 0,
    "rr_valid": 0,
}

days = pd.Series(pd.to_datetime(m5.ts_start, unit="ns", utc=True).tz_convert("America/New_York").date).drop_duplicates().tolist()

for d in days:
    funnel["total_days"] += 1
    ctx = sb.compute_day_context(b_eur, d, window, daily_df)
    if ctx is None: continue
    funnel["has_daily_ctx"] += 1
    if ctx.dol_side == 0: continue
    funnel["dol_non_zero"] += 1
    if ctx.adr_exhausted: continue
    funnel["adr_not_exhausted"] += 1
    
    # Check window M5 indices
    ws_ns = pd.Timestamp(d).tz_localize("America/New_York").tz_convert("UTC").value + (sh * 3600 + sm * 60) * 1_000_000_000
    we_ns = pd.Timestamp(d).tz_localize("America/New_York").tz_convert("UTC").value + (eh * 3600 + em * 60) * 1_000_000_000
    m5_start = int(np.searchsorted(m5.ts_start, ws_ns))
    m5_end = int(np.searchsorted(m5.ts_start, we_ns))
    if m5_end <= m5_start: continue
    
    sweep_ok = False
    disp_ok = False
    mss_ok = False
    fvg_ok = False
    stop_ok = False
    rr_ok = False
    
    target_side = ctx.dol_side
    for k in range(m5_start, m5_end):
        if not np.isfinite(m5.atr[k]) or m5.atr[k] <= 0: continue
        if target_side == 1:
            p_idx = sb.latest_confirmed_pivot(pl5, k, right=2)
            if p_idx < 0 or not (m5.l[k] < m5.l[p_idx]): continue
        else:
            p_idx = sb.latest_confirmed_pivot(ph5, k, right=2)
            if p_idx < 0 or not (m5.h[k] > m5.h[p_idx]): continue
        sweep_ok = True
        
        for k2 in range(k + 1, min(k + 6, m5_end)):
            rng2 = m5.h[k2] - m5.l[k2]
            if rng2 <= 0: continue
            if abs(m5.c[k2] - m5.o[k2]) / rng2 < sb.BODY_RATIO_MIN: continue
            if rng2 < sb.RANGE_ATR_MULT * m5.atr[k2 - 1]: continue
            disp_ok = True
            
            if target_side == 1:
                opp_idx = sb.latest_confirmed_pivot(ph5, k2, right=2)
                if opp_idx < 0 or opp_idx < p_idx or not (m5.c[k2] > m5.h[opp_idx]): continue
            else:
                opp_idx = sb.latest_confirmed_pivot(pl5, k2, right=2)
                if opp_idx < 0 or opp_idx < p_idx or not (m5.c[k2] < m5.l[opp_idx]): continue
            mss_ok = True
            
            k3 = k2 + 1
            if k3 >= len(m5.o): continue
            k1 = k2 - 1
            if target_side == 1:
                if not (m5.l[k3] > m5.h[k1]): continue
                dist = m5.h[k1] - (min(m5.l[k:k2+1]) - 1.5 * 0.0001)
            else:
                if not (m5.h[k3] < m5.l[k1]): continue
                dist = (max(m5.h[k:k2+1]) + 1.5 * 0.0001) - m5.l[k1]
            fvg_ok = True
            
            if sp.min_stop <= dist <= sp.max_stop:
                stop_ok = True
                rr_ok = True
                break
        if rr_ok: break
        
    if sweep_ok: funnel["sweep_found"] += 1
    if disp_ok: funnel["disp_found"] += 1
    if mss_ok: funnel["mss_found"] += 1
    if fvg_ok: funnel["fvg_found"] += 1
    if stop_ok: funnel["stop_in_bounds"] += 1
    if rr_ok: funnel["rr_valid"] += 1

print("Funnel for EURUSD AM over 6 years:")
for k, v in funnel.items():
    print(f"  {k:20s}: {v}")
