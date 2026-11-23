"""Test the curated high-edge Silver Bullet portfolio across all profitable slots.
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

CURATED_SLOTS = [
    ("GBPUSD", "LDN"),
    ("EURUSD", "AM"),
    ("USATECHIDXUSD", "AM"),
    ("USATECHIDXUSD", "PM"),
    ("USA500IDXUSD", "AM"),
    ("USDJPY", "AM"),
]

# Ensure London recalibration is set
sb.WINDOWS["LDN"] = ((3, 0), (4, 0))
sb.SESSION_ENDS["LDN"] = (8, 0)
sb.SPECS["GBPUSD"] = sb.Spec(min_stop=0.0015, max_stop=0.0035, slip=0.00005, commission_rt=0.00006)

bars = {}
for sym in set(s[0] for s in CURATED_SLOTS):
    bars[sym] = sb.prepare(load_m1_symbol(sym))

for period, start_d, end_d in [
    ("IN-SAMPLE DEV (2021-2024)", "2021-01-01", "2024-12-31"),
    ("OUT-OF-SAMPLE HO (2025-2026)", "2025-01-01", "2026-12-31"),
    ("COMBINED 6-YEARS (2021-2026)", "2021-01-01", "2026-12-31"),
]:
    trades = []
    for sym, win in CURATED_SLOTS:
        t = sb.run_slot_c22(bars[sym], sym, win, start_d, end_d, cal_df)
        if not t.empty:
            t["slot"] = f"{sym}_{win}"
            trades.append(t)
            
    port = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame()
    m = compute_metrics(port)
    print("=" * 80)
    print(f"{period}")
    print("=" * 80)
    print(f"Total Trades:           {m['n']}")
    print(f"Win Rate:               {m['win_rate']*100:.1f}%")
    print(f"Profit Factor:          {m['pf']:.2f}")
    print(f"Mean Return:            {m['mean_r']:+.3f} R")
    print(f"Max Drawdown:           {m['max_dd_r']:.2f} R")
    for s in sorted(port["slot"].unique()):
        sub = port[port["slot"] == s]
        sm = compute_metrics(sub)
        print(f"  {s:20s} n={sm['n']:2d} | WR={sm['win_rate']*100:4.1f}% | PF={sm['pf']:4.2f} | MeanR={sm['mean_r']:+5.3f}R")
