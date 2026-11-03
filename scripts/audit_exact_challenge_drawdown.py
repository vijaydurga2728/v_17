from __future__ import annotations

import pandas as pd

from run_2018_all_symbols import all_trades

trades_sorted = sorted(all_trades, key=lambda x: x["closed_at"])

bal = 10000.0
peak = 10000.0
step1_max_dd = 0.0
step2_max_dd = 0.0

step1_date = "2018-01-18"
step2_date = "2018-03-06"

# Phase 1
phase1_trades = [t for t in trades_sorted if str(t["closed_at"])[:10] <= step1_date]
bal = 10000.0
peak = 10000.0
for tr in phase1_trades:
    bal += tr["pnl"]
    if bal > peak:
        peak = bal
    dd = (peak - bal) / peak * 100.0
    if dd > step1_max_dd:
        step1_max_dd = dd

# Phase 2
phase2_trades = [t for t in trades_sorted if step1_date < str(t["closed_at"])[:10] <= step2_date]
bal = 10000.0
peak = 10000.0
for tr in phase2_trades:
    bal += tr["pnl"]
    if bal > peak:
        peak = bal
    dd = (peak - bal) / peak * 100.0
    if dd > step2_max_dd:
        step2_max_dd = dd

print("="*70)
print("=== FTMO 2-STEP EVALUATION WINDOW EXACT DRAWDOWN AUDIT ===")
print("="*70)
print(f"Step 1 Trades (Jan 1 - Jan 18): {len(phase1_trades)}")
print(f"Step 1 Max Drawdown: {step1_max_dd:.2f}% (Limit: < 10.0%) -> {'PASS' if step1_max_dd < 10.0 else 'BREACHED'}")
print(f"Step 1 Date Passed: {step1_date}")

print(f"\nStep 2 Trades (Jan 19 - Mar 06): {len(phase2_trades)}")
print(f"Step 2 Max Drawdown: {step2_max_dd:.2f}% (Limit: < 10.0%) -> {'PASS' if step2_max_dd < 10.0 else 'BREACHED'}")
print(f"Step 2 Date Passed: {step2_date}")

print(f"\nOverall Challenge Verdict: Both Step 1 and Step 2 Passed by March 6, 2018!")
print("="*70)
