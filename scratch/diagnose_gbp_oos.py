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

sb.WINDOWS["LDN_KZ"] = ((2, 0), (5, 0))
sb.SESSION_ENDS["LDN_KZ"] = (8, 0)
sb.SPECS["GBPUSD"] = sb.Spec(min_stop=0.0010, max_stop=0.0035, slip=0.00005, commission_rt=0.00006)

t_ho = sb.run_slot_c22(b_gbp, "GBPUSD", "LDN_KZ", "2025-01-01", "2026-12-31", cal_df)

print("=" * 80)
print(f"DIAGNOSING GBPUSD OOS (2025-2026) TRADES: Total {len(t_ho)}")
print("=" * 80)

# Long vs Short breakdown
longs = t_ho[t_ho["side"] == 1]
shorts = t_ho[t_ho["side"] == -1]

m_long = compute_metrics(longs)
m_short = compute_metrics(shorts)

print(f"LONGS:  n={m_long['n']:2d} | WR={m_long['win_rate']*100:4.1f}% | PF={m_long['pf']:5.2f} | MeanR={m_long['mean_r']:+6.3f}R | Total R={longs['r'].sum():+.2f}")
print(f"SHORTS: n={m_short['n']:2d} | WR={m_short['win_rate']*100:4.1f}% | PF={m_short['pf']:5.2f} | MeanR={m_short['mean_r']:+6.3f}R | Total R={shorts['r'].sum():+.2f}")

# Stop distance distribution
print("\nRisk Distance (Stop Pips) Distribution:")
t_ho["stop_pips"] = t_ho["risk_dist"] * 10000
print(t_ho.groupby(pd.cut(t_ho["stop_pips"], bins=[10, 15, 20, 25, 30, 35])).agg(
    n=("r", "count"),
    wins=("r", lambda s: (s > 0).sum()),
    mean_r=("r", "mean"),
    tot_r=("r", "sum"),
))

# Reason for exit
print("\nExit Reasons:")
print(t_ho["reason"].value_counts())

# Time of entry (hour in NY)
t_ho["entry_dt"] = pd.to_datetime(b_gbp.ts[t_ho["fill_i"].to_numpy()], unit="ns", utc=True).tz_convert(sb.NY)
t_ho["entry_hour"] = t_ho["entry_dt"].dt.hour
print("\nTrades by Entry Hour (NY Time):")
print(t_ho.groupby("entry_hour").agg(
    n=("r", "count"),
    wr=("r", lambda s: (s > 0).mean() * 100),
    mean_r=("r", "mean"),
    tot_r=("r", "sum"),
))
