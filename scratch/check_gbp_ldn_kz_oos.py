"""Evaluate London Killzone GBPUSD on Holdout (2025-2026).
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

sb.WINDOWS["LDN_KZ"] = ((2, 0), (5, 0))
sb.SESSION_ENDS["LDN_KZ"] = (8, 0)
sb.SPECS["GBPUSD"] = sb.Spec(min_stop=0.0010, max_stop=0.0035, slip=0.00005, commission_rt=0.00006)

# Dev
t_dev = sb.run_slot_c22(b_gbp, "GBPUSD", "LDN_KZ", "2021-01-01", "2024-12-31", cal_df)
m_dev = compute_metrics(t_dev)

# Holdout (2025-2026)
t_ho = sb.run_slot_c22(b_gbp, "GBPUSD", "LDN_KZ", "2025-01-01", "2026-12-31", cal_df)
m_ho = compute_metrics(t_ho)

print("=" * 80)
print("LONDON KILLZONE GBPUSD (02:00 - 05:00 NY) - DEV vs HOLDOUT (OOS)")
print("=" * 80)
print(f"DEV [2021-2024]: n={m_dev['n']} | WR={m_dev['win_rate']*100:.1f}% | PF={m_dev['pf']:.2f} | MeanR={m_dev['mean_r']:+.3f}R | MaxDD={m_dev['max_dd_r']:.1f}R")
print(f"HO  [2025-2026]: n={m_ho['n']} | WR={m_ho['win_rate']*100:.1f}% | PF={m_ho['pf']:.2f} | MeanR={m_ho['mean_r']:+.3f}R | MaxDD={m_ho['max_dd_r']:.1f}R")
print("=" * 80)
