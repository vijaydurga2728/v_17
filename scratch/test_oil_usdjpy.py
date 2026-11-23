"""Test LIGHTCMDUSD and USDJPY Silver Bullet performance across windows."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_calendar_blackout_df, compute_metrics
from v17.setups import c22_silver_bullet as sb

cal_df = load_calendar_blackout_df()

# Add specs
sb.SPECS["LIGHTCMDUSD"] = sb.Spec(min_stop=0.20, max_stop=1.80, slip=0.03, commission_rt=0.0)
sb.SPECS["USDJPY"] = sb.Spec(min_stop=0.060, max_stop=0.350, slip=0.005, commission_rt=0.006)

symbols = ["LIGHTCMDUSD", "USDJPY"]

for sym in symbols:
    p = REPO / "data" / "bars_m1_paired" / sym
    df = pd.read_parquet(p)
    b = sb.prepare(df)
    print("=" * 80, flush=True)
    print(f"TESTING {sym} ACROSS SESSIONS", flush=True)
    print("=" * 80, flush=True)
    
    for win in ["AM", "PM", "LDN"]:
        t_dev = sb.run_slot_c22(b, sym, win, "2021-01-01", "2024-12-31", cal_df)
        t_ho = sb.run_slot_c22(b, sym, win, "2025-01-01", "2026-12-31", cal_df)
        
        m_dev = compute_metrics(t_dev)
        m_ho = compute_metrics(t_ho)
        
        print(f"[{win:3s}] {sym:12s} | DEV [2021-2024] n={m_dev['n']:3d} | PF={m_dev['pf']:5.2f} | win={m_dev['win_rate']*100:4.1f}% | meanR={m_dev['mean_r']:+6.3f}R | DD={m_dev['max_dd_r']:4.1f}R", flush=True)
        print(f"      {' '*12} | HO  [2025-2026] n={m_ho['n']:3d} | PF={m_ho['pf']:5.2f} | win={m_ho['win_rate']*100:4.1f}% | meanR={m_ho['mean_r']:+6.3f}R | DD={m_ho['max_dd_r']:4.1f}R", flush=True)
