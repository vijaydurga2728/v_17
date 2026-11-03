from __future__ import annotations

import pandas as pd

from run_2018_all_symbols import all_trades

gbp_trades = [t for t in all_trades if t["symbol"] == "GBPUSD"]
trades_sorted = sorted(gbp_trades, key=lambda x: x["closed_at"])

bal = 10000.0
peak = 10000.0
max_dd = 0.0

step1_passed = False
step1_date = None
step2_passed = False
step2_date = None
step = 1

step1_trades = []
step2_trades = []

for tr in trades_sorted:
    bal += tr["pnl"]
    if bal > peak:
        peak = bal
    dd = (peak - bal) / peak * 100.0
    if dd > max_dd:
        max_dd = dd
        
    if step == 1:
        step1_trades.append(tr)
        if bal >= 11000.0:
            step1_passed = True
            step1_date = str(tr["closed_at"])[:10]
            step = 2
            bal = 10000.0
            peak = 10000.0
    elif step == 2:
        step2_trades.append(tr)
        if bal >= 10500.0:
            step2_passed = True
            step2_date = str(tr["closed_at"])[:10]
            step = 3

pnls = [t["pnl"] for t in trades_sorted]
wins = sum(1 for p in pnls if p > 0)
gross_win = sum(p for p in pnls if p > 0)
gross_loss = abs(sum(p for p in pnls if p < 0))
pf = gross_win / gross_loss if gross_loss > 0 else 0.0

print("="*70)
print("=== GBPUSD STANDALONE FTMO CHALLENGE AUDIT (2018) ===")
print("="*70)
print(f"Total Trades: {len(trades_sorted)}")
print(f"Wins: {wins}, Losses: {len(trades_sorted) - wins}")
print(f"Win Rate: {wins/len(trades_sorted)*100:.1f}%")
print(f"Profit Factor: {pf:.2f}")
print(f"Total Net PnL: ${sum(pnls):+.2f}")
print(f"Max Portfolio Drawdown: {max_dd:.2f}% (FTMO Limit: < 10.0%)")
print(f"Step 1 Passed: {step1_passed} on {step1_date} (after {len(step1_trades)} trades)")
print(f"Step 2 Passed: {step2_passed} on {step2_date} (after {len(step2_trades)} trades)")
print(f"FTMO Evaluation Result: {'PASSED & FUNDED' if step1_passed and step2_passed and max_dd < 10.0 else 'INCOMPLETE'}")
print("="*70)
