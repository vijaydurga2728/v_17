"""Comprehensive Audit of Grade-A Institutional Portfolio:
1. 12-Fold Walk-Forward Stability (R11, R12)
2. Spread Stress Test at Baseline, +50%, +100% (R19)
3. Full Statistical Metrics
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_calendar_blackout_df, compute_metrics, load_m1_symbol
from v17.setups import c22_silver_bullet as sb

cal_df = load_calendar_blackout_df()

# Grade-A Curated Institutional Portfolio
slots = sb.CURATED_SLOTS

print("=" * 80, flush=True)
print("1. GRADE-A CURATED PORTFOLIO 12-FOLD WALK-FORWARD AUDIT", flush=True)
print("=" * 80, flush=True)

symbols = sorted(list({s for _, s in slots}))
bars = {s: sb.prepare(load_m1_symbol(s)) for s in symbols}

# Collect all trades 2021-2026
all_trades = []
for win, sym in slots:
    t = sb.run_slot_c22(bars[sym], sym, win, "2021-01-01", "2026-12-31", cal_df)
    if not t.empty:
        t["slot"] = f"{sym}_{win}"
        all_trades.append(t)

df = pd.concat(all_trades, ignore_index=True)
df["dt"] = pd.to_datetime(df["day"])
df = df.sort_values("dt").reset_index(drop=True)

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
    sub = df[(df["dt"] >= s_d) & (df["dt"] <= e_d)]
    m = compute_metrics(sub)
    passed = (m["pf"] >= 1.0) and (m["mean_r"] >= 0.0) and (m["n"] > 0)
    if passed:
        passed_folds += 1
    status = "PASS" if passed else "FAIL"
    print(f"Fold {name:7s} [{s_d} to {e_d}] | n={m['n']:2d} | WR={m['win_rate']*100:4.1f}% | PF={m['pf']:5.2f} | MeanR={m['mean_r']:+6.3f}R | DD={m['max_dd_r']:4.1f}R | {status}", flush=True)

ratio = passed_folds / len(folds)
print(f"\nWalk-Forward Passed Folds: {passed_folds}/{len(folds)} ({ratio*100:.1f}%) | Target >= 60%", flush=True)

print("\n" + "=" * 80, flush=True)
print("2. RULE R19: SPREAD & SLIPPAGE STRESS TEST (+50% and +100%)", flush=True)
print("=" * 80, flush=True)

# Stress test function
def run_stress(multiplier: float):
    stressed_trades = []
    for win, sym in slots:
        b = bars[sym]
        half_spread = (b.ask_c - b.bid_c) / 2.0 * multiplier
        b_stress = sb.Bars(
            ts=b.ts,
            bid_o=b.mid_o - half_spread, bid_h=b.mid_h - half_spread,
            bid_l=b.mid_l - half_spread, bid_c=b.mid_c - half_spread,
            ask_o=b.mid_o + half_spread, ask_h=b.mid_h + half_spread,
            ask_l=b.mid_l + half_spread, ask_c=b.mid_c + half_spread,
            mid_o=b.mid_o, mid_h=b.mid_h, mid_l=b.mid_l, mid_c=b.mid_c,
            atr=b.atr,
        )
        orig_spec = sb.SPECS[sym]
        sb.SPECS[sym] = sb.Spec(
            min_stop=orig_spec.min_stop,
            max_stop=orig_spec.max_stop,
            slip=orig_spec.slip * multiplier,
            commission_rt=orig_spec.commission_rt,
        )
        t_ho = sb.run_slot_c22(b_stress, sym, win, "2025-01-01", "2026-12-31", cal_df)
        sb.SPECS[sym] = orig_spec  # restore
        if not t_ho.empty:
            stressed_trades.append(t_ho)
            
    df_st = pd.concat(stressed_trades, ignore_index=True) if stressed_trades else pd.DataFrame()
    m = compute_metrics(df_st)
    return m

m_base = run_stress(1.0)
m_50 = run_stress(1.5)
m_100 = run_stress(2.0)

print(f"Baseline (1.0x Cost): n={m_base['n']} | WR={m_base['win_rate']*100:.1f}% | PF={m_base['pf']:.2f} | MeanR={m_base['mean_r']:+.3f}R | MaxDD={m_base['max_dd_r']:.2f}R", flush=True)
print(f"Stress 1 (+50% Cost): n={m_50['n']} | WR={m_50['win_rate']*100:.1f}% | PF={m_50['pf']:.2f} | MeanR={m_50['mean_r']:+.3f}R | MaxDD={m_50['max_dd_r']:.2f}R", flush=True)
print(f"Stress 2 (+100% Cost): n={m_100['n']} | WR={m_100['win_rate']*100:.1f}% | PF={m_100['pf']:.2f} | MeanR={m_100['mean_r']:+.3f}R | MaxDD={m_100['max_dd_r']:.2f}R", flush=True)

r19_passed = (m_50['pf'] >= 1.0) and (m_100['pf'] >= 1.0)
print(f"\nRule R19 Result: {'PASS' if r19_passed else 'FAIL'}", flush=True)
print("=" * 80, flush=True)
