import pandas as pd
from datetime import datetime, UTC
from decimal import Decimal
from v17.common.types import Symbol
from v17.backtest.cli import _load_bars_1m
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.setups.silver_bullet import SilverBullet
from v17.setups.judas_swing import JudasSwing
from v17.risk.engine import DefaultRiskEngine
from v17.backtest.metrics import winrate, profit_factor, max_drawdown_pct

start = datetime(2021, 1, 1, tzinfo=UTC)
end = datetime(2021, 12, 31, 23, 59, tzinfo=UTC)

symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'EURGBP', 'USATECHIDXUSD']
print(f"=== Starting 2021 Out-of-Sample Verification across {symbols} ===")

results = {}
for sym_str in symbols:
    sym = Symbol(sym_str)
    print(f"\n--- Loading 2021 bars for {sym_str} ---")
    bars = _load_bars_1m(sym, start, end)
    if bars.empty:
        print(f"No bars for {sym_str}")
        continue
    print(f"Precomputing structure for {sym_str} ({len(bars):,} 1m bars)...")
    pre = precompute(bars, sym)
    
    setups = [SilverBullet(), JudasSwing()]
    loop = EventLoop(sym, setups, DefaultRiskEngine(), pre, calendar=None)
    print(f"Running 2021 EventLoop for {sym_str}...")
    closed, eq = loop.run(start, end, Decimal("10000"))
    pnls = [t.pnl for t in closed]
    mdd = max_drawdown_pct(list(eq['equity'])) if not eq.empty else 0.0
    tot = sum(pnls) if pnls else Decimal("0")
    wr = winrate(pnls) * 100 if pnls else 0.0
    pf = profit_factor(pnls) if pnls else 0.0
    results[sym_str] = {
        'trades': len(closed),
        'wr': wr,
        'pf': pf,
        'mdd': mdd,
        'tot': tot,
        'closed': closed
    }
    print(f"RESULT 2021 {sym_str}: Trades={len(closed)}, WR={wr:.1f}%, PF={pf:.2f}, MaxDD={mdd:.2f}%, NetPnL=${tot:,.2f}")

print("\n" + "="*60)
print("=== 2021 OUT-OF-SAMPLE FINAL RESULTS SUMMARY ===")
print(f"{'Symbol':15} | {'Trades':6} | {'WinRate':7} | {'PF':5} | {'MaxDD':6} | {'Net PnL ($)':12}")
print("-" * 60)
for sym_str, r in results.items():
    print(f"{sym_str:15} | {r['trades']:6} | {r['wr']:6.1f}% | {r['pf']:5.2f} | {r['mdd']:5.2f}% | ${r['tot']:+10.2f}")
print("="*60)
