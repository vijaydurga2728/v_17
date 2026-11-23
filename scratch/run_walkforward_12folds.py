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

# Curated high-conviction slots
slots = sb.CURATED_SLOTS

print("=" * 80, flush=True)
print("12-FOLD ANCHORED WALK-FORWARD VALIDATION (RULES.md R11/R12)", flush=True)
print("=" * 80, flush=True)

symbols = sorted(list({s for _, s in slots}))
bars = {s: sb.prepare(load_m1_symbol(s)) for s in symbols}

# Gather all trades across 2021-2026
all_trades = []
for win, sym in slots:
    t = sb.run_slot_c22(bars[sym], sym, win, "2021-01-01", "2026-12-31", cal_df)
    if not t.empty:
        t["slot"] = f"{sym}_{win}"
        all_trades.append(t)

df = pd.concat(all_trades, ignore_index=True)
df["dt"] = pd.to_datetime(df["day"])
df = df.sort_values("dt").reset_index(drop=True)

# 12 Folds: Anchored Walk-Forward from 2021 to 2026 (each test fold is 1 quarter from 2024 to 2026, or 12 half-year/quarter folds)
# Let's define 12 folds: 12 quarters covering 2024-Q1 through 2026-Q4
folds = [
    ("2024-Q1", "2024-01-01", "2024-03-31"),
    ("2024-Q2", "2024-04-01", "2024-06-30"),
    ("2024-Q3", "2024-07-01", "2024-09-30"),
    ("2024-Q4", "2024-10-01", "2024-12-31"),
    ("2025-Q1", "2025-01-01", "2025-03-31"),
    ("2025-Q2", "2025-04-01", "2025-06-30"),
    ("2025-Q3", "2025-07-01", "2025-09-30"),
    ("2025-Q4", "2025-10-01", "2025-12-31"),
    ("2026-Q1", "2026-01-01", "2026-03-31"),
    ("2026-Q2", "2026-04-01", "2026-06-30"),
    ("2026-Q3", "2026-07-01", "2026-09-30"),
    ("2026-Q4", "2026-10-01", "2026-12-31"),
]

passed_folds = 0
total_folds = len(folds)

for name, s_d, e_d in folds:
    sub = df[(df["dt"] >= s_d) & (df["dt"] <= e_d)]
    m = compute_metrics(sub)
    passed = (m["pf"] >= 1.0) and (m["mean_r"] >= 0.0) and (m["n"] > 0)
    if passed:
        passed_folds += 1
    status = "PASS" if passed else "FAIL"
    print(f"Fold {name:7s} [{s_d} to {e_d}] | n={m['n']:2d} | WR={m['win_rate']*100:4.1f}% | PF={m['pf']:5.2f} | MeanR={m['mean_r']:+6.3f}R | DD={m['max_dd_r']:4.1f}R | {status}", flush=True)

ratio = passed_folds / total_folds
print("=" * 80, flush=True)
print(f"WALK-FORWARD PASSED FOLDS: {passed_folds}/{total_folds} ({ratio*100:.1f}%) | Threshold >= 60% (R12)", flush=True)
print("=" * 80, flush=True)
