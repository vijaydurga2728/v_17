import sys
from pathlib import Path
import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))
from v17.setups import c25_silver_bullet_institutional as c25
from run_c22_silver_bullet import load_m1_symbol, compute_metrics, load_calendar_blackout_df

cal_df = load_calendar_blackout_df()

for sym in ["USA30IDXUSD", "USATECHIDXUSD", "USA500IDXUSD"]:
    print(f"\n{'='*60}\nEVALUATING SYMBOL: {sym}\n{'='*60}")
    b = c25.prepare(load_m1_symbol(sym))
    daily_df = c25.build_daily_df(b)
    
    for period_name, s_date, e_date in [
        ("DEV 2021-2024", "2021-01-01", "2024-12-31"),
        ("OOS 2025-2026", "2025-01-01", "2026-12-31"),
        ("STRESS 2015-2016", "2015-01-01", "2016-12-31"),
    ]:
        t = c25.run_slot_c25(b, sym, "OPEN_DRIVE", s_date, e_date, cal_df)
        if t.empty:
            continue
            
        # Classify trades: Inside Range Expansion vs Outside Breakout Fade
        inside_mask = []
        for idx, row in t.iterrows():
            d = pd.Timestamp(row["day"]).date()
            d_row = daily_df[daily_df["date"] == d].iloc[0]
            pdh, pdl = float(d_row["pdh"]), float(d_row["pdl"])
            d0_ns = pd.Timestamp(d).tz_localize(c25.NY).tz_convert("UTC").value
            ws_ns = d0_ns + (9 * 3600 + 30 * 60) * 1_000_000_000
            i_start = np.searchsorted(b.ts, d0_ns)
            i_ws = np.searchsorted(b.ts, ws_ns)
            intra_h = float(np.max(b.mid_h[i_start:i_ws]))
            intra_l = float(np.min(b.mid_l[i_start:i_ws]))
            
            pdl_swept = (intra_l < pdl)
            pdh_swept = (intra_h > pdh)
            
            # If price stayed inside yesterday's range before 9:30, it is an Inside Range Expansion
            is_inside = not pdl_swept and not pdh_swept
            inside_mask.append(is_inside)
            
        t["is_inside"] = inside_mask
        m_inside = compute_metrics(t[t["is_inside"]])
        m_outside = compute_metrics(t[~t["is_inside"]])
        m_all = compute_metrics(t)
        
        print(f"\n--- {period_name} ---")
        print(f"  ALL TRADES:     n={m_all['n']:3d} | WR={m_all['win_rate']*100:4.1f}% | PF={m_all['pf']:4.2f} | MeanR={m_all['mean_r']:+6.3f}R | DD={m_all['max_dd_r']:4.1f}R")
        print(f"  INSIDE RANGE:   n={m_inside['n']:3d} | WR={m_inside['win_rate']*100:4.1f}% | PF={m_inside['pf']:4.2f} | MeanR={m_inside['mean_r']:+6.3f}R | DD={m_inside['max_dd_r']:4.1f}R")
        print(f"  OUTSIDE (FADE): n={m_outside['n']:3d} | WR={m_outside['win_rate']*100:4.1f}% | PF={m_outside['pf']:4.2f} | MeanR={m_outside['mean_r']:+6.3f}R | DD={m_outside['max_dd_r']:4.1f}R")
