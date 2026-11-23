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

for sym, win in [("EURUSD", "AM"), ("GBPUSD", "LDN_SB"), ("USATECHIDXUSD", "AM"), ("USA500IDXUSD", "AM")]:
    b = sb.prepare(load_m1_symbol(sym))
    t = sb.run_slot_c22(b, sym, win, "2021-01-01", "2026-12-31", cal_df)
    t["dt"] = pd.to_datetime(t["day"])
    # Filter holiday
    t = t[~((t["dt"].dt.month == 12) & (t["dt"].dt.day >= 20))].reset_index(drop=True)
    
    print(f"\n=== {sym} ({win}) Total Trades: {len(t)} ===")
    w = t[t["r"] > 0]
    l = t[t["r"] <= 0]
    print(f"Overall: WR {len(w)/len(t)*100:.1f}% ({len(w)}W / {len(l)}L), PF: {w['r'].sum()/abs(l['r'].sum()):.2f}, Net: {t['r'].sum():+.2f}R")
    
    # Check by side (Long vs Short)
    for s, name in [(1, "LONGS"), (-1, "SHORTS")]:
        sub = t[t["side"] == s]
        if len(sub) > 0:
            sw = sub[sub["r"] > 0]
            sl = sub[sub["r"] <= 0]
            wr = len(sw)/len(sub)*100
            pf = sw["r"].sum()/abs(sl["r"].sum()) if len(sl) > 0 else 999.0
            print(f"  {name:6s}: {len(sub):2d} trades | WR: {wr:5.1f}% ({len(sw)}W/{len(sl)}L) | PF: {pf:4.2f} | Net: {sub['r'].sum():+5.2f}R")
    
    # Check RR and reasons
    print("  Exit Reasons:", t["reason"].value_counts().to_dict())
