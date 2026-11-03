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

s = get_settings()
START = datetime(2018, 1, 1, tzinfo=UTC)
END = datetime(2018, 12, 31, 23, 59, tzinfo=UTC)

all_trades = []

for sym_str in ["GBPUSD", "USATECHIDXUSD"]:
    sym = Symbol(sym_str)
    df = read_1m(sym, START, END, s.parquet_root)
    pre = precompute(df, sym)
    setups = [JudasSwing(), SilverBullet()]
    loop = EventLoop(sym, setups, DefaultRiskEngine(), pre)
    trades, equity = loop.run(START, END, Decimal("10000"))
    for t in trades:
        all_trades.append({
            "symbol": sym_str,
            "opened_at": t.opened_at,
            "closed_at": t.closed_at,
            "pnl": float(t.pnl) if t.pnl is not None else 0.0,
            "reason": t.reason,
        })

trades_sorted = sorted(all_trades, key=lambda x: x["closed_at"])
bal = 10000.0
peak = 10000.0
max_dd = 0.0

step = 1
step1_passed = False
step2_passed = False
step1_date = None
step2_date = None

for tr in trades_sorted:
    bal += tr["pnl"]
    if bal > peak:
        peak = bal
    dd = (peak - bal) / peak * 100.0
    if dd > max_dd:
        max_dd = dd
    if step == 1:
        if bal >= 11000.0:
            step1_passed = True
            step1_date = str(tr["closed_at"])[:10]
            step = 2
            bal = 10000.0
            peak = 10000.0
    elif step == 2:
        if bal >= 10500.0:
            step2_passed = True
            step2_date = str(tr["closed_at"])[:10]
            step = 3

print("=== GBPUSD + NAS100 COMBINED (2018) ===")
print(f"Total Trades: {len(trades_sorted)}")
print(f"Total Net PnL: ${sum(t['pnl'] for t in trades_sorted):+.2f}")
print(f"Max Peak-to-Trough Drawdown: {max_dd:.2f}% (FTMO limit < 10%)")
print(f"Step 1 Passed: {step1_passed} (Date: {step1_date})")
print(f"Step 2 Passed: {step2_passed} (Date: {step2_date})")
