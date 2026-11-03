from __future__ import annotations

import pandas as pd

from run_2018_all_symbols import all_trades

# Test with 0.5% per trade risk (standard for 5-symbol portfolio to maintain total portfolio risk < 2%)
# Currently all_trades used 1% risk ($100 per 10k). Scaling by 0.5 means pnl * 0.5.

trades_sorted = sorted(all_trades, key=lambda x: x["closed_at"])

bal = 10000.0
peak = 10000.0
max_dd = 0.0

step1_passed = False
step1_date = None
step2_passed = False
step2_date = None
step = 1

step1_max_dd = 0.0
step2_max_dd = 0.0
step1_trades = []
step2_trades = []

for tr in trades_sorted:
    # 0.5% risk scaling
    pnl = tr["pnl"] * 0.5
    bal += pnl
    if bal > peak:
        peak = bal
    dd = (peak - bal) / peak * 100.0
    
    if step == 1:
        step1_trades.append(tr)
        if dd > step1_max_dd:
            step1_max_dd = dd
        if bal >= 11000.0:  # +10% target hit
            step1_passed = True
            step1_date = str(tr["closed_at"])[:10]
            step = 2
            bal = 10000.0
            peak = 10000.0
    elif step == 2:
        step2_trades.append(tr)
        if dd > step2_max_dd:
            step2_max_dd = dd
        if bal >= 10500.0:  # +5% target hit
            step2_passed = True
            step2_date = str(tr["closed_at"])[:10]
            step = 3

print("="*70)
print("=== 5-SYMBOL PORTFOLIO WITH 0.5% RISK (INSTITUTIONAL PORTFOLIO SIZING) ===")
print("="*70)
print(f"Total Trades Evaluated: {len(trades_sorted)}")
print(f"\nStep 1 (Target +10% / +$1,000):")
print(f"  Passed: {step1_passed} on {step1_date} (after {len(step1_trades)} trades)")
print(f"  Max Drawdown in Step 1: {step1_max_dd:.2f}% (Limit: < 10.0%) -> {'PASS' if step1_max_dd < 10.0 else 'BREACHED'}")

print(f"\nStep 2 (Target +5% / +$500):")
print(f"  Passed: {step2_passed} on {step2_date} (after {len(step2_trades)} trades)")
print(f"  Max Drawdown in Step 2: {step2_max_dd:.2f}% (Limit: < 10.0%) -> {'PASS' if step2_max_dd < 10.0 else 'BREACHED'}")

print(f"\nOverall FTMO Challenge Status: {'PASSED & FULLY FUNDED' if step1_passed and step2_passed and step1_max_dd < 10.0 and step2_max_dd < 10.0 else 'INCOMPLETE'}")
print("="*70)
