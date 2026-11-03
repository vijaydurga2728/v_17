from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import pandas as pd

from v17.common.types import Symbol, Side
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.risk.engine import DefaultRiskEngine
from v17.setups.silver_bullet import SilverBullet
from v17.setups.judas_swing import JudasSwing
from v17.data.parquet_store import read_1m
from v17.config import get_settings
from v17.backtest.metrics import profit_factor

s = get_settings()
START = datetime(2018, 1, 1, tzinfo=UTC)
END = datetime(2018, 12, 31, 23, 59, tzinfo=UTC)

symbols = [
    Symbol("GBPUSD"),
    Symbol("USATECHIDXUSD"),
]

symbol_results = []
all_trades = []

print("=== RUNNING 2018 EVALUATION FOR FOCUSED PORTFOLIO (GBPUSD + NAS100) ===")
print("Features active: Dynamic Liquidity Targets, 2.0x Dynamic Scaling, Automated Daily Risk Circuit Breaker")

for sym in symbols:
    df = read_1m(sym, START, END, s.parquet_root)
    print(f"\nProcessing {sym} ({len(df):,} bars)...")
    pre = precompute(df, sym)
    
    setups = [JudasSwing(), SilverBullet()]
    loop = EventLoop(sym, setups, DefaultRiskEngine(), pre)
    trades, equity = loop.run(START, END, Decimal("10000"))
    
    pnls = [t.pnl for t in trades if t.pnl is not None]
    pf = profit_factor(pnls) if pnls else 0.0
    wins = sum(1 for p in pnls if p > 0)
    wr = (wins / len(pnls) * 100) if pnls else 0.0
    dd = loop.max_floating_dd_pct
    net_pnl = sum(pnls) if pnls else Decimal("0")
    
    symbol_results.append({
        "Symbol": str(sym),
        "Trades": len(trades),
        "Wins": wins,
        "Losses": len(trades) - wins,
        "WinRate%": round(wr, 1),
        "ProfitFactor": round(pf, 2),
        "MaxDD%": round(dd, 2),
        "NetPnL": round(float(net_pnl), 2),
    })
    
    for t in trades:
        all_trades.append({
            "symbol": str(sym),
            "opened_at": t.opened_at,
            "closed_at": t.closed_at,
            "pnl": float(t.pnl) if t.pnl is not None else 0.0,
            "side": t.side.value,
            "reason": t.reason,
        })

res_df = pd.DataFrame(symbol_results)
print("\n" + "="*70)
print("=== 2018 FOCUSED PORTFOLIO INDIVIDUAL PERFORMANCE ===")
print("="*70)
print(res_df.to_string(index=False))

# --- FTMO 2-STEP EVALUATION ---
print("\n" + "="*70)
print("=== FTMO 2-STEP CHALLENGE AUDIT (GBPUSD + NAS100) ===")
print("="*70)

trades_chronological = sorted(all_trades, key=lambda x: x["closed_at"])

account_balance = 10000.0
peak_balance = 10000.0
max_overall_dd = 0.0

step1_passed = False
step1_date = None
step2_passed = False
step2_date = None

step1_start_bal = 10000.0
current_bal = step1_start_bal
step = 1

step1_trades = []
step2_trades = []

for tr in trades_chronological:
    current_bal += tr["pnl"]
    
    if current_bal > peak_balance:
        peak_balance = current_bal
    dd = (peak_balance - current_bal) / peak_balance * 100.0
    if dd > max_overall_dd:
        max_overall_dd = dd
        
    if step == 1:
        step1_trades.append(tr)
        if current_bal >= 11000.0:  # +10% target hit
            step1_passed = True
            step1_date = str(tr["closed_at"])[:10]
            step = 2
            current_bal = 10000.0
            peak_balance = 10000.0
    elif step == 2:
        step2_trades.append(tr)
        if current_bal >= 10500.0:  # +5% target hit
            step2_passed = True
            step2_date = str(tr["closed_at"])[:10]
            step = 3

print(f"Total Portfolio Trades in 2018: {len(trades_chronological)}")
total_net = sum(t["pnl"] for t in trades_chronological)
print(f"Total Portfolio Combined PnL: ${total_net:+.2f}")

print(f"\nStep 1 (10% Target = $1,000):")
print(f"  Passed: {'YES' if step1_passed else 'NO'}")
if step1_passed:
    print(f"  Passed on Date: {step1_date} (after {len(step1_trades)} trades)")
    
print(f"\nStep 2 (5% Target = $500):")
print(f"  Passed: {'YES' if step2_passed else 'NO'}")
if step2_passed:
    print(f"  Passed on Date: {step2_date} (after {len(step2_trades)} trades)")

print(f"\nFTMO Drawdown Guardrails:")
print(f"  Max Drawdown Observed: {max_overall_dd:.2f}% (Limit: < 10.0%)")
print(f"  Overall Compliance: {'PASS' if max_overall_dd < 10.0 else 'BREACHED'}")
