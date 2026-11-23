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

sb.SPECS["EURUSD"] = sb.Spec(min_stop=0.0006, max_stop=0.0025, slip=0.00005, commission_rt=0.00006)
sb.SPECS["USATECHIDXUSD"] = sb.Spec(min_stop=8.0, max_stop=50.0, slip=0.5, commission_rt=0.0)

b_eur = sb.prepare(load_m1_symbol("EURUSD"))
b_nq = sb.prepare(load_m1_symbol("USATECHIDXUSD"))

t_eur = sb.run_slot_c22(b_eur, "EURUSD", "AM", "2021-01-01", "2026-12-31", cal_df)
t_eur["pillar"] = "EURUSD_AM"

t_nq = sb.run_slot_c22(b_nq, "USATECHIDXUSD", "AM", "2021-01-01", "2026-12-31", cal_df)
t_nq = t_nq[t_nq["side"] == 1].copy()
t_nq["pillar"] = "NQ_AM_LONGS"

all_t = pd.concat([t_eur, t_nq], ignore_index=True)
all_t["dt"] = pd.to_datetime(all_t["day"])
all_t = all_t[~((all_t["dt"].dt.month == 12) & (all_t["dt"].dt.day >= 20))].reset_index(drop=True)
all_t = all_t.sort_values(["dt", "fill_i"]).reset_index(drop=True)

all_t["ym"] = all_t["dt"].dt.to_period("M")

# Monthly summary
m_summary = all_t.groupby("ym").agg(
    trades=("r", "count"),
    wins=("r", lambda x: (x > 0).sum()),
    losses=("r", lambda x: (x <= 0).sum()),
    net_r=("r", "sum")
).reset_index()

m_summary["win_rate"] = (m_summary["wins"] / m_summary["trades"]) * 100.0

# Calculate Payouts for $100k account (1.0% risk = $1,000 / 1R)
# FTMO Profit Split: 80% to trader
m_summary["gross_profit_100k"] = m_summary["net_r"] * 1000.0
m_summary["ftmo_payout_80pct"] = m_summary["gross_profit_100k"].apply(lambda p: max(0.0, p * 0.80))

# For $10k account (0.5% risk = $50 / 1R)
m_summary["gross_profit_10k"] = m_summary["net_r"] * 50.0
m_summary["ftmo_payout_10k"] = m_summary["gross_profit_10k"].apply(lambda p: max(0.0, p * 0.80))

print("MONTH-BY-MONTH RESULTS & FTMO PAYOUTS:")
print(m_summary.to_string())

print("\nANNUAL SUMMARY:")
all_t["year"] = all_t["dt"].dt.year
y_summary = all_t.groupby("year").agg(
    trades=("r", "count"),
    wins=("r", lambda x: (x > 0).sum()),
    losses=("r", lambda x: (x <= 0).sum()),
    net_r=("r", "sum")
).reset_index()
y_summary["win_rate"] = (y_summary["wins"] / y_summary["trades"]) * 100.0
y_summary["payout_100k"] = y_summary["net_r"] * 1000.0 * 0.80
print(y_summary.to_string())
