from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import pandas as pd

from v17.common.types import Symbol
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.risk.engine import DefaultRiskEngine
from v17.setups.silver_bullet import SilverBullet
from v17.data.parquet_store import read_1m
from v17.config import get_settings
from v17.backtest.metrics import profit_factor

s = get_settings()
START = datetime(2018, 1, 1, tzinfo=UTC)
END = datetime(2018, 12, 31, 23, 59, tzinfo=UTC)

symbols = [
    Symbol("EURUSD"),
    Symbol("GBPUSD"),
    Symbol("USDJPY"),
    Symbol("EURGBP"),
    Symbol("USATECHIDXUSD"),
]

symbol_results = []
all_trades = []

print("=== RUNNING PURE SILVER BULLET STANDALONE ACROSS ALL 5 SYMBOLS (2018) ===")

for sym in symbols:
    df = read_1m(sym, START, END, s.parquet_root)
    pre = precompute(df, sym)
    
    # PURE SILVER BULLET ONLY
    setups = [SilverBullet()]
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
            "closed_at": t.closed_at,
            "pnl": float(t.pnl) if t.pnl is not None else 0.0,
        })

res_df = pd.DataFrame(symbol_results)
print("\n" + "="*70)
print("=== 2018 PURE SILVER BULLET PER-SYMBOL RESULTS ===")
print("="*70)
print(res_df.to_string(index=False))

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

for tr in trades_sorted:
    bal += tr["pnl"]
    if bal > peak:
        peak = bal
    dd = (peak - bal) / peak * 100.0
    if dd > max_dd:
        max_dd = dd
    if step == 1:
        if dd > step1_max_dd:
            step1_max_dd = dd
        if bal >= 11000.0:
            step1_passed = True
            step1_date = str(tr["closed_at"])[:10]
            step = 2
            bal = 10000.0
            peak = 10000.0
    elif step == 2:
        if dd > step2_max_dd:
            step2_max_dd = dd
        if bal >= 10500.0:
            step2_passed = True
            step2_date = str(tr["closed_at"])[:10]
            step = 3

print("\n" + "="*70)
print(f"Total Combined Trades: {len(trades_sorted)}")
print(f"Total Net PnL: ${sum(t['pnl'] for t in trades_sorted):+.2f}")
print(f"Step 1 Passed: {step1_passed} ({step1_date}), Step 1 Max DD: {step1_max_dd:.2f}%")
print(f"Step 2 Passed: {step2_passed} ({step2_date}), Step 2 Max DD: {step2_max_dd:.2f}%")
print(f"Full Year Max Drawdown: {max_dd:.2f}%")
print("="*70)
