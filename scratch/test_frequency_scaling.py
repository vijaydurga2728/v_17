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

sb.WINDOWS["PM"] = ((14, 0), (15, 0))
sb.SESSION_ENDS["PM"] = (16, 30)
sb.WINDOWS["LDN"] = ((3, 0), (4, 0))
sb.SESSION_ENDS["LDN"] = (8, 0)
sb.WINDOWS["AM"] = ((10, 0), (11, 0))
sb.SESSION_ENDS["AM"] = (16, 30)

sb.SPECS["EURUSD"] = sb.Spec(min_stop=0.0006, max_stop=0.0025, slip=0.00005, commission_rt=0.00006)
sb.SPECS["GBPUSD"] = sb.Spec(min_stop=0.0015, max_stop=0.0035, slip=0.00005, commission_rt=0.00006)
sb.SPECS["USATECHIDXUSD"] = sb.Spec(min_stop=8.0, max_stop=50.0, slip=0.5, commission_rt=0.0)
sb.SPECS["USA500IDXUSD"] = sb.Spec(min_stop=1.5, max_stop=15.0, slip=0.5, commission_rt=0.0)

results = []

for sym in ["EURUSD", "GBPUSD", "USATECHIDXUSD", "USA500IDXUSD"]:
    b = sb.prepare(load_m1_symbol(sym))
    for win in ["LDN", "AM", "PM"]:
        t = sb.run_slot_c22(b, sym, win, "2021-01-01", "2026-12-31", cal_df)
        if len(t) == 0:
            continue
        t["symbol"] = sym
        t["window"] = win
        results.append(t)
        w = t[t["r"] > 0]
        l = t[t["r"] <= 0]
        wr = len(w)/len(t)*100
        pf = w["r"].sum() / abs(l["r"].sum()) if len(l) > 0 else 999.0
        print(f"{sym:14s} {win:4s} | Trades: {len(t):3d} | WR: {wr:5.1f}% ({len(w):2d}W / {len(l):2d}L) | PF: {pf:4.2f} | Net: {t['r'].sum():+6.2f} R")

all_df = pd.concat(results, ignore_index=True)
all_df["dt"] = pd.to_datetime(all_df["day"])
all_df = all_df[~((all_df["dt"].dt.month == 12) & (all_df["dt"].dt.day >= 20))].reset_index(drop=True)

tot_w = all_df[all_df["r"] > 0]
tot_l = all_df[all_df["r"] <= 0]
print("=" * 80)
print(f"TOTAL MULTI-SESSION PORTFOLIO: {len(all_df)} Trades | WR: {len(tot_w)/len(all_df)*100:.1f}% | Net: {all_df['r'].sum():+.2f} R")
print(f"Trades per year: {len(all_df) / 5.5:.1f} trades/year (~{len(all_df) / 66:.1f} trades/month)")
