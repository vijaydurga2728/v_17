"""Cycle 22 — Unified Portfolio Runner: London Judas Swing + NY AM Institutional Silver Bullet.

Pairs:
1. London Judas Swing (02:00-05:00 NY): GBPUSD & EURUSD
2. NY AM Institutional Silver Bullet (10:00-11:00 NY): EURUSD & USATECHIDXUSD

Evaluates monthly trade frequency, win rate, and FTMO drawdown metrics over 2021-2024.
"""
from __future__ import annotations

from datetime import datetime, UTC
from decimal import Decimal
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from v17.common.types import Symbol
from v17.backtest.precompute import precompute
from v17.backtest.loop import EventLoop
from v17.risk.engine import DefaultRiskEngine
from v17.setups.judas_swing import JudasSwing
from v17.setups.silver_bullet import SilverBullet
from v17.data.parquet_store import read_1m
from v17.config import get_settings
from v17.backtest.metrics import profit_factor

s = get_settings()
START = datetime(2021, 1, 1, tzinfo=UTC)
END = datetime(2024, 12, 31, 23, 59, tzinfo=UTC)

PORTFOLIO_CONFIG = [
    {"sym": Symbol("GBPUSD"), "setups": [JudasSwing()]},
    {"sym": Symbol("EURUSD"), "setups": [JudasSwing(), SilverBullet()]},
    {"sym": Symbol("USATECHIDXUSD"), "setups": [SilverBullet()]},
]


def main() -> int:
    print("=" * 80)
    print("CYCLE 22: UNIFIED FTMO PORTFOLIO (LONDON JUDAS + NY SILVER BULLET)")
    print("Period: 2021-2024 (48 Months) | Account Size: $10,000 | Risk: Default Engine")
    print("=" * 80)
    
    all_trades = []
    symbol_summaries = []
    
    for cfg in PORTFOLIO_CONFIG:
        sym = cfg["sym"]
        setups = cfg["setups"]
        setup_names = "+".join(s.name for s in setups)
        print(f"\nProcessing {sym} ({setup_names})...")
        
        df = read_1m(sym, START, END, s.parquet_root)
        if df.empty:
            print(f"  Warning: No data for {sym}")
            continue
        print(f"  Loaded {len(df):,} M1 bars.")
        
        pre = precompute(df, sym)
        loop = EventLoop(sym, setups, DefaultRiskEngine(), pre)
        trades, equity = loop.run(START, END, Decimal("10000"))
        
        pnls = [t.pnl for t in trades if t.pnl is not None]
        pf = profit_factor(pnls) if pnls else 0.0
        wins = sum(1 for p in pnls if p > 0)
        n = len(pnls)
        wr = (wins / n * 100) if n else 0.0
        dd = loop.max_floating_dd_pct
        net_pnl = sum(pnls) if pnls else Decimal("0")
        trades_mo = n / 48.0
        
        symbol_summaries.append({
            "Symbol": str(sym),
            "Setups": setup_names,
            "Trades": n,
            "Trades/Mo": round(trades_mo, 2),
            "WinRate%": round(wr, 1),
            "ProfitFactor": round(pf, 2),
            "MaxDD%": round(float(dd), 2),
            "NetPnL": round(float(net_pnl), 2),
        })
        
        for t in trades:
            all_trades.append({
                "symbol": str(sym),
                "signal_id": t.signal_id,
                "setup": setup_names,
                "opened_at": t.opened_at,
                "closed_at": t.closed_at,
                "pnl": float(t.pnl) if t.pnl is not None else 0.0,
                "side": t.side.value,
                "reason": t.reason,
            })
            
    print("\n" + "=" * 80)
    print("=== INDIVIDUAL COMPONENT PERFORMANCE (2021-2024) ===")
    print("=" * 80)
    res_df = pd.DataFrame(symbol_summaries)
    print(res_df.to_string(index=False))
    
    if all_trades:
        trades_chronological = sorted(all_trades, key=lambda x: x["closed_at"])
        n_tot = len(trades_chronological)
        wins_tot = sum(1 for t in trades_chronological if t["pnl"] > 0)
        losses_tot = sum(1 for t in trades_chronological if t["pnl"] <= 0)
        wr_tot = (wins_tot / n_tot * 100) if n_tot else 0.0
        net_tot = sum(t["pnl"] for t in trades_chronological)
        
        win_sum = sum(t["pnl"] for t in trades_chronological if t["pnl"] > 0)
        loss_sum = -sum(t["pnl"] for t in trades_chronological if t["pnl"] < 0)
        pf_tot = (win_sum / loss_sum) if loss_sum > 0 else float("inf")
        
        # Drawdown computation
        peak = 10000.0
        cur = 10000.0
        max_dd = 0.0
        for t in trades_chronological:
            cur += t["pnl"]
            if cur > peak:
                peak = cur
            dd = (peak - cur) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
                
        print("\n" + "=" * 80)
        print("=== UNIFIED PORTFOLIO TOTALS (ALL ENGINES COMBINED) ===")
        print("=" * 80)
        print(f"Total Trades:           {n_tot} trades across 48 months")
        print(f"Average Monthly Trades: {n_tot / 48.0:.2f} trades / month (Target: 4-6 trades/mo)")
        print(f"Portfolio Win Rate:     {wr_tot:.1f}%")
        print(f"Portfolio Profit Factor:{pf_tot:.2f}")
        print(f"Total Net PnL:          ${net_tot:,.2f}")
        print(f"Maximum Equity DD:      {max_dd:.2f}% (FTMO Limit: < 10.0%)")
        print("=" * 80)
        
        pd.DataFrame(trades_chronological).to_csv(REPO / "out" / "c22_unified_portfolio_trades.csv", index=False)
        res_df.to_csv(REPO / "out" / "c22_unified_portfolio_summary.csv", index=False)
        
    return 0


if __name__ == "__main__":
    sys.exit(main())
