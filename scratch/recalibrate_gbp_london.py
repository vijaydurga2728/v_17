"""Recalibrate London GBPUSD to be robust across BOTH Dev (2021-2024) AND Holdout (2025-2026).
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
m1_gbp = load_m1_symbol("GBPUSD")
b_gbp = sb.prepare(m1_gbp)

# Test various windows and min_stops
# Window: 03:00-05:00 NY (08:00-10:00 London local) vs 02:00-05:00 NY
for win_name, (wh_s, wm_s), (wh_e, wm_e) in [
    ("LDN_02_05", (2, 0), (5, 0)),
    ("LDN_03_05", (3, 0), (5, 0)),
    ("LDN_03_04", (3, 0), (4, 0)),
]:
    sb.WINDOWS[win_name] = ((wh_s, wm_s), (wh_e, wm_e))
    sb.SESSION_ENDS[win_name] = (8, 0)
    
    for min_stop in [0.0010, 0.0015, 0.0018]:
        sb.SPECS["GBPUSD"] = sb.Spec(min_stop=min_stop, max_stop=0.0035, slip=0.00005, commission_rt=0.00006)
        
        t_dev = sb.run_slot_c22(b_gbp, "GBPUSD", win_name, "2021-01-01", "2024-12-31", cal_df)
        t_ho = sb.run_slot_c22(b_gbp, "GBPUSD", win_name, "2025-01-01", "2026-12-31", cal_df)
        
        m_dev = compute_metrics(t_dev)
        m_ho = compute_metrics(t_ho)
        
        # Combined 6-year metrics
        all_t = pd.concat([t_dev, t_ho], ignore_index=True)
        m_all = compute_metrics(all_t)
        
        print(f"[{win_name} | min_stop={min_stop*10000:.0f}p]")
        print(f"  DEV (2021-24): n={m_dev['n']:3d} | WR={m_dev['win_rate']*100:4.1f}% | PF={m_dev['pf']:4.2f} | MeanR={m_dev['mean_r']:+5.3f}R")
        print(f"  HO  (2025-26): n={m_ho['n']:3d} | WR={m_ho['win_rate']*100:4.1f}% | PF={m_ho['pf']:4.2f} | MeanR={m_ho['mean_r']:+5.3f}R")
        print(f"  ALL (6 YEARS): n={m_all['n']:3d} | WR={m_all['win_rate']*100:4.1f}% | PF={m_all['pf']:4.2f} | MeanR={m_all['mean_r']:+5.3f}R | MaxDD={m_all['max_dd_r']:4.1f}R")
        print("-" * 75)
