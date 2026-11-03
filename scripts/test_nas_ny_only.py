import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
import pandas as pd
from v17.common.types import TF, Symbol
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.risk.engine import DefaultRiskEngine
from v17.setups.silver_bullet import SilverBullet
from v17.setups.judas_swing import JudasSwing
from v17.backtest import cost
from v17.setups import sessions

SYMBOL = Symbol('USATECHIDXUSD')
START = datetime(2015, 1, 1, tzinfo=UTC)
END = datetime(2017, 12, 31, tzinfo=UTC)

df = pd.read_parquet('data/cache_nas100_pre.parquet')
print(f'Loaded cached bars: {len(df):,}')
pre = precompute(df, SYMBOL)

# Let's test combinations:
# 1. Full vs NY-only windows for NAS100
# 2. Dynamic R:R vs fixed TP points

print('--- EXPERIMENT 1: NY Windows Only vs All Windows ---')
# Default windows: ((3,0),(4,0)), ((10,0),(11,0)), ((14,0),(15,0))
# NY-only windows: ((10,0),(11,0)), ((14,0),(15,0))
for tp in [50, 60, 80]:
    cost.TP_FALLBACK_PIPS_BY_SYMBOL['USATECHIDXUSD'] = Decimal(str(tp))
    
    # Run with all windows
    sessions.SB_WINDOWS = (
        (sessions.time(3, 0), sessions.time(4, 0)),
        (sessions.time(10, 0), sessions.time(11, 0)),
        (sessions.time(14, 0), sessions.time(15, 0)),
    )
    loop = EventLoop(SYMBOL, [SilverBullet(), JudasSwing()], DefaultRiskEngine(), pre)
    trades_all, _ = loop.run(START, END, Decimal('10000'))
    wins_all = sum(1 for t in trades_all if t.pnl and t.pnl > 0)
    gw = sum(t.pnl for t in trades_all if t.pnl and t.pnl > 0)
    gl = abs(sum(t.pnl for t in trades_all if t.pnl and t.pnl < 0))
    pf_all = float(gw / gl) if gl > 0 else 999.0
    pnl_all = sum(t.pnl for t in trades_all if t.pnl)
    dd_all = loop.max_floating_dd_pct
    print(f'ALL WINS | TP {tp:2d} | Trades: {len(trades_all):2d} | WR: {wins_all/len(trades_all)*100:4.1f}% | PF: {pf_all:4.2f} | MaxDD: {dd_all:5.2f}% | PnL: ${float(pnl_all):>+7.2f}')
    
    # Run with NY-only windows
    sessions.SB_WINDOWS = (
        (sessions.time(10, 0), sessions.time(11, 0)),
        (sessions.time(14, 0), sessions.time(15, 0)),
    )
    loop = EventLoop(SYMBOL, [SilverBullet(), JudasSwing()], DefaultRiskEngine(), pre)
    trades_ny, _ = loop.run(START, END, Decimal('10000'))
    wins_ny = sum(1 for t in trades_ny if t.pnl and t.pnl > 0)
    gw_ny = sum(t.pnl for t in trades_ny if t.pnl and t.pnl > 0)
    gl_ny = abs(sum(t.pnl for t in trades_ny if t.pnl and t.pnl < 0))
    pf_ny = float(gw_ny / gl_ny) if gl_ny > 0 else 999.0
    pnl_ny = sum(t.pnl for t in trades_ny if t.pnl)
    dd_ny = loop.max_floating_dd_pct
    print(f'NY ONLY  | TP {tp:2d} | Trades: {len(trades_ny):2d} | WR: {wins_ny/len(trades_ny)*100:4.1f}% | PF: {pf_ny:4.2f} | MaxDD: {dd_ny:5.2f}% | PnL: ${float(pnl_ny):>+7.2f}')
