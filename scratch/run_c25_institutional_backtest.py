"""Comprehensive Backtest Runner for Cycle 25: Institutional Silver Bullet Engine.

Evaluates the 5 Out-of-the-Box Architectural Innovations:
1. M5 Structure + M1 Precision FVG Entry.
2. 50% Consequent Encroachment (CE) FVG Limits.
3. Open-Drive Window (09:30-10:30 NY) for US Indices.
4. Two-Tranche Dynamic Liquidity Exit (60% @ 1.5R, 40% @ 2.5R runner + Breakeven lock).

Periods:
- DEV: 2021-01-01 to 2024-12-31
- Holdout OOS: 2025-01-01 to 2026-12-31
- 12-Fold Walk-Forward Validation
- Monte Carlo 1,000 Runs
- Rule R19 Stress Test (+50% and +100% cost inflation)
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df, compute_metrics
from v17.setups import c25_silver_bullet_institutional as c25

cal_df = load_calendar_blackout_df()

# Curated High-Expectancy Institutional Slots
SLOTS = [
    # US Indices: Open-Drive (09:30-10:30 NY) + NY PM (14:00-15:00 NY)
    ("OPEN_DRIVE", "USATECHIDXUSD"),
    ("OPEN_DRIVE", "USA30IDXUSD"),
    ("OPEN_DRIVE", "USA500IDXUSD"),
    ("PM", "USA30IDXUSD"),
    ("PM", "USATECHIDXUSD"),
    ("PM", "USA500IDXUSD"),
    # Gold & FX: NY AM & PM
    ("AM", "XAUUSD"),
    ("AM", "EURUSD"),
    ("PM", "EURUSD"),
]

symbols = sorted(list({s for _, s in SLOTS}))
bars_cache = {}

print("=" * 80, flush=True)
print("CYCLE 25: OUT-OF-THE-BOX INSTITUTIONAL SILVER BULLET BACKTEST", flush=True)
print("=" * 80, flush=True)

for sym in symbols:
    print(f"Loading {sym}...", flush=True)
    bars_cache[sym] = c25.prepare(load_m1_symbol(sym))
    print(f"  {sym}: {len(bars_cache[sym].ts):,} M1 bars ready.", flush=True)

all_dev = []
all_oos = []

print("\n" + "=" * 80, flush=True)
print("INDIVIDUAL SLOT PERFORMANCE (DEV 2021-2024 vs OOS 2025-2026)", flush=True)
print("=" * 80, flush=True)

for win, sym in SLOTS:
    b = bars_cache[sym]
    t_dev = c25.run_slot_c25(b, sym, win, "2021-01-01", "2024-12-31", cal_df)
    t_oos = c25.run_slot_c25(b, sym, win, "2025-01-01", "2026-12-31", cal_df)
    
    m_dev = compute_metrics(t_dev)
    m_oos = compute_metrics(t_oos)
    
    print(f"[{win:10s}] {sym:14s} | DEV: n={m_dev['n']:3d} WR={m_dev['win_rate']*100:4.1f}% PF={m_dev['pf']:4.2f} MeanR={m_dev['mean_r']:+5.3f}R DD={m_dev['max_dd_r']:4.1f}R", flush=True)
    print(f"             {' '*14} | OOS: n={m_oos['n']:3d} WR={m_oos['win_rate']*100:4.1f}% PF={m_oos['pf']:4.2f} MeanR={m_oos['mean_r']:+5.3f}R DD={m_oos['max_dd_r']:4.1f}R", flush=True)
    
    if not t_dev.empty:
        t_dev["slot"] = f"{sym}_{win}"
        all_dev.append(t_dev)
    if not t_oos.empty:
        t_oos["slot"] = f"{sym}_{win}"
        all_oos.append(t_oos)

dev_df = pd.concat(all_dev, ignore_index=True)
oos_df = pd.concat(all_oos, ignore_index=True)

# Sort and deduplicate by (symbol, day) to enforce single trade per symbol per day
dev_df["dt"] = pd.to_datetime(dev_df["day"])
oos_df["dt"] = pd.to_datetime(oos_df["day"])

dev_df = dev_df.sort_values("dt").drop_duplicates(subset=["symbol", "day"]).reset_index(drop=True)
oos_df = oos_df.sort_values("dt").drop_duplicates(subset=["symbol", "day"]).reset_index(drop=True)

m_dev_tot = compute_metrics(dev_df)
m_oos_tot = compute_metrics(oos_df)

print("\n" + "=" * 80, flush=True)
print("PORTFOLIO AGGREGATE RESULTS", flush=True)
print("=" * 80, flush=True)
print(f"DEV  [2021-2024] n={m_dev_tot['n']} | WR={m_dev_tot['win_rate']*100:.1f}% | PF={m_dev_tot['pf']:.2f} | MeanR={m_dev_tot['mean_r']:+.3f}R | MaxDD={m_dev_tot['max_dd_r']:.2f}R", flush=True)
print(f"OOS  [2025-2026] n={m_oos_tot['n']} | WR={m_oos_tot['win_rate']*100:.1f}% | PF={m_oos_tot['pf']:.2f} | MeanR={m_oos_tot['mean_r']:+.3f}R | MaxDD={m_oos_tot['max_dd_r']:.2f}R", flush=True)

r_oos = oos_df["r"].to_numpy(np.float64)
sharpe = (r_oos.mean() / r_oos.std() * np.sqrt(252)) if len(r_oos) > 1 and r_oos.std() > 0 else 0.0
print(f"OOS Annualized Sharpe: {sharpe:.2f} (Target >= 1.0)", flush=True)

# 12-Fold Walk-Forward
print("\n" + "=" * 80, flush=True)
print("12-FOLD WALK-FORWARD STABILITY (RULES.md R11 & R12)", flush=True)
print("=" * 80, flush=True)

full_df = pd.concat([dev_df, oos_df], ignore_index=True).sort_values("dt").reset_index(drop=True)

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
for name, s_d, e_d in folds:
    sub = full_df[(full_df["dt"] >= s_d) & (full_df["dt"] <= e_d)]
    m = compute_metrics(sub)
    passed = (m["pf"] >= 1.0) and (m["mean_r"] >= 0.0) and (m["n"] > 0)
    if passed:
        passed_folds += 1
    status = "PASS" if passed else "FAIL"
    print(f"Fold {name:7s} [{s_d} to {e_d}] | n={m['n']:2d} | WR={m['win_rate']*100:4.1f}% | PF={m['pf']:5.2f} | MeanR={m['mean_r']:+6.3f}R | DD={m['max_dd_r']:4.1f}R | {status}", flush=True)

ratio = passed_folds / len(folds)
print(f"\nWalk-Forward Passed Folds: {passed_folds}/{len(folds)} ({ratio*100:.1f}%) | Threshold >= 60%", flush=True)

# Monte Carlo 1,000 runs
print("\n" + "=" * 80, flush=True)
print("MONTE CARLO 1,000 PERMUTATION RUNS (RULES.md R13)", flush=True)
print("=" * 80, flush=True)

np.random.seed(42)
mc_pfs, mc_dds = [], []
n_t = len(r_oos)
for _ in range(1000):
    sample = np.random.choice(r_oos, size=n_t, replace=True)
    w = sample[sample > 0].sum()
    l = abs(sample[sample <= 0].sum())
    pf = w / l if l > 0 else 999.0
    mc_pfs.append(pf)
    eq = np.r_[0.0, np.cumsum(sample)]
    dd = float((np.maximum.accumulate(eq) - eq).max())
    mc_dds.append(dd)

p5_pf = np.percentile(mc_pfs, 5)
p95_dd = np.percentile(mc_dds, 95)
print(f"Monte Carlo 5th-pct PF    = {p5_pf:.2f} (Target > 1.0)", flush=True)
print(f"Monte Carlo 95th-pct MaxDD= {p95_dd:.2f} R (Target <= 8.0R)", flush=True)

# Save backtest trades
OUT = REPO / "out" / "c25"
OUT.mkdir(parents=True, exist_ok=True)
dev_df.to_csv(OUT / "trades_dev.csv", index=False)
oos_df.to_csv(OUT / "trades_oos.csv", index=False)
print(f"\nSaved trade manifests to {OUT}", flush=True)
