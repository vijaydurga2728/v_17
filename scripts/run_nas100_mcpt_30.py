from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
import pandas as pd
from v17.common.types import Symbol
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.risk.engine import DefaultRiskEngine
from v17.setups.silver_bullet import SilverBullet
from v17.validation.mcpt import permute_bars
from v17.backtest.metrics import profit_factor
from v17.backtest import cost

cost.TP_FALLBACK_PIPS_BY_SYMBOL["USATECHIDXUSD"] = Decimal("70")

df = pd.read_parquet("data/cache_nas100_pre.parquet")
START = datetime(2015, 1, 1, tzinfo=UTC)
END = datetime(2017, 12, 31, tzinfo=UTC)
sym = Symbol("USATECHIDXUSD")

print(f"Loaded {len(df):,} cached bars for {sym} (2015-2017)")

# Real run
pre = precompute(df, sym)
loop = EventLoop(sym, [SilverBullet()], DefaultRiskEngine(), pre)
real_trades, real_eq = loop.run(START, END, Decimal("10000"))
real_pnls = [t.pnl for t in real_trades if t.pnl is not None]
real_pf = profit_factor(real_pnls) if real_pnls else 0.0
wins = sum(1 for p in real_pnls if p > 0)
wr = (wins / len(real_pnls) * 100) if real_pnls else 0.0
dd = loop.max_floating_dd_pct
net_pnl = sum(real_pnls) if real_pnls else Decimal("0")

print(f"\n=== REAL NAS100 STRATEGY BASELINE ===")
print(f"Trades: {len(real_trades)}")
print(f"Win Rate: {wr:.1f}% ({wins}W / {len(real_trades)-wins}L)")
print(f"Profit Factor: {real_pf:.2f}")
print(f"Max Drawdown: {dd:.2f}%")
print(f"Net PnL: ${float(net_pnl):+.2f}")

# 30-Permutation Monte Carlo Permutation Test
runs = 30
seed = 42
better_count = 0
perm_pfs: list[float] = []

print(f"\n=== RUNNING 30 MCPT PERMUTATIONS ===")
for i in range(runs):
    perm_seed = seed + i * 1000 + 1
    perm_bars = permute_bars(df, seed=perm_seed)
    p_pre = precompute(perm_bars, sym)
    p_loop = EventLoop(sym, [SilverBullet()], DefaultRiskEngine(), p_pre)
    p_trades, _ = p_loop.run(START, END, Decimal("10000"))
    p_pnls = [t.pnl for t in p_trades if t.pnl is not None]
    p_pf = profit_factor(p_pnls) if p_pnls else 0.0
    perm_pfs.append(p_pf)
    if p_pf >= real_pf:
        better_count += 1
    print(f"  Permutation {i+1:2d}/{runs} (seed={perm_seed}): trades={len(p_trades):2d} | PF={p_pf:5.2f} | exceed_real={'YES' if p_pf >= real_pf else 'NO'}")

p_value = (1.0 + better_count) / (float(runs) + 1.0)
passed = p_value < 0.05

print(f"\n=== MCPT 30-COMBINATIONS FINAL AUDIT ===")
print(f"Real PF: {real_pf:.2f}")
print(f"Permutations Meeting or Exceeding Real PF: {better_count}/{runs}")
print(f"Min Permuted PF: {min(perm_pfs):.2f}")
print(f"Max Permuted PF: {max(perm_pfs):.2f}")
print(f"Mean Permuted PF: {sum(perm_pfs)/len(perm_pfs):.2f}")
print(f"Empirical p-value: {p_value:.4f}")
status = "PASSED (p < 0.05 - Statistical Edge Verified)" if passed else "FAILED (p >= 0.05 - No Edge Over Noise)"
print(f"Verdict: {status}")
