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

def run_year(year: int, symbols: list[str]):
    start = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year, 12, 31, 23, 59, tzinfo=UTC)
    print(f"\n============================================================")
    print(f"=== Running Full-Year {year} Backtest (Standard Config) ===")
    print(f"============================================================")
    results = {}
    for sym_str in symbols:
        sym = Symbol(sym_str)
        bars = _load_bars_1m(sym, start, end)
        if bars.empty:
            print(f"No bars for {sym_str} in {year}")
            continue
        pre = precompute(bars, sym)
        setups = [SilverBullet(), JudasSwing()]
        loop = EventLoop(sym, setups, DefaultRiskEngine(), pre, calendar=None)
        closed, eq = loop.run(start, end, Decimal("10000"))
        pnls = [t.pnl for t in closed if t.pnl is not None]
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
        }
        print(f"{year} {sym_str:14} | Trades={len(closed):3} | WR={wr:5.1f}% | PF={pf:4.2f} | MaxDD={mdd:4.2f}% | NetPnL=${tot:+9.2f}")
    return results

if __name__ == "__main__":
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'EURGBP', 'USATECHIDXUSD']
    r2019 = run_year(2019, symbols)
    r2021 = run_year(2021, symbols)
