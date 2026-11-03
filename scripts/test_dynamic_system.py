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

for sym_str in ["GBPUSD", "USATECHIDXUSD"]:
    sym = Symbol(sym_str)
    df = read_1m(sym, START, END, s.parquet_root)
    print(f"\n--- Baseline 2018 for {sym} ({len(df):,} bars) ---")
    pre = precompute(df, sym)
    setups = [JudasSwing(), SilverBullet()]
    loop = EventLoop(sym, setups, DefaultRiskEngine(), pre)
    trades, equity = loop.run(START, END, Decimal("10000"))
    pnls = [t.pnl for t in trades if t.pnl is not None]
    pf = profit_factor(pnls) if pnls else 0.0
    wins = sum(1 for p in pnls if p > 0)
    wr = (wins / len(pnls) * 100) if pnls else 0.0
    net = sum(pnls) if pnls else Decimal("0")
    print(f"Trades: {len(trades)}, Wins: {wins}, WR: {wr:.1f}%, PF: {pf:.2f}, MaxDD: {loop.max_floating_dd_pct:.2f}%, Net: ${net:+.2f}")
