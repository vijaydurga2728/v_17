import sys
from pathlib import Path
import pandas as pd
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df
import v17.setups.c22_silver_bullet as sb

cal_df = load_calendar_blackout_df()

sb.WINDOWS["LDN_SB"] = ((3, 0), (4, 0))
sb.SESSION_ENDS["LDN_SB"] = (8, 0)
sb.SPECS["GBPUSD"] = sb.Spec(min_stop=0.0015, max_stop=0.0035, slip=0.00005, commission_rt=0.00006)
sb.SPECS["USATECHIDXUSD"] = sb.Spec(min_stop=8.0, max_stop=50.0, slip=0.5, commission_rt=0.0)
sb.SPECS["USA500IDXUSD"] = sb.Spec(min_stop=1.5, max_stop=15.0, slip=0.5, commission_rt=0.0)

for sym, win in [("GBPUSD", "LDN_SB"), ("USATECHIDXUSD", "AM"), ("USA500IDXUSD", "AM")]:
    b = sb.prepare(load_m1_symbol(sym))
    t = sb.run_slot_c22(b, sym, win, "2021-01-01", "2026-12-31", cal_df)
    w = t[t["r"] > 0]
    l = t[t["r"] <= 0]
    wr = len(w) / len(t) * 100.0 if len(t) > 0 else 0
    pf = w["r"].sum() / abs(l["r"].sum()) if len(l) > 0 else 999.0
    print(f"Baseline C22 {sym:14s} {win:6s}: {len(t):2d} trades | WR: {wr:5.1f}% | PF: {pf:4.2f} | Net: {t['r'].sum():+6.2f} R")
