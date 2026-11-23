import sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df
import v17.setups.c22_silver_bullet as sb

cal_df = load_calendar_blackout_df()

b_gbp = sb.prepare(load_m1_symbol("GBPUSD"))
t_gbp_am = sb.run_slot_c22(b_gbp, "GBPUSD", "AM", "2021-01-01", "2026-12-31", cal_df)
t_gbp_am["dt"] = pd.to_datetime(t_gbp_am["day"])
t_gbp_am = t_gbp_am[~((t_gbp_am["dt"].dt.month == 12) & (t_gbp_am["dt"].dt.day >= 20))].reset_index(drop=True)

w = t_gbp_am[t_gbp_am["r"] > 0]
l = t_gbp_am[t_gbp_am["r"] <= 0]
wr = len(w)/len(t_gbp_am)*100 if len(t_gbp_am) > 0 else 0
pf = w["r"].sum() / abs(l["r"].sum()) if len(l) > 0 else 999.0
print(f"GBPUSD NY AM: {len(t_gbp_am)} trades | WR: {wr:.1f}% ({len(w)}W / {len(l)}L) | PF: {pf:.2f} | Net: {t_gbp_am['r'].sum():+.2f}R")
for s, name in [(1, "LONGS"), (-1, "SHORTS")]:
    sub = t_gbp_am[t_gbp_am["side"] == s]
    if len(sub) > 0:
        sw = sub[sub["r"] > 0]
        sl = sub[sub["r"] <= 0]
        print(f"  {name:6s}: {len(sub):2d} trades | WR: {len(sw)/len(sub)*100:5.1f}% | PF: {sw['r'].sum()/abs(sl['r'].sum()):4.2f} | Net: {sub['r'].sum():+5.2f}R")
