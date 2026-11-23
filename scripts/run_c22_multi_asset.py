"""Cycle 22 — Multi-Asset Universe Evaluation (8 Instruments).

Evaluates the Institutional Silver Bullet across:
- FX Majors: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD
- US Indices: USATECHIDXUSD (NQ), USA500IDXUSD (ES), USA30IDXUSD (YM)

Sessions: NY AM (10:00-11:00 NY) and NY PM (14:00-15:00 NY)
Period: 2021-01-01 -> 2024-12-31 (48 months)
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df, compute_metrics  # noqa: E402
from v17.setups import c22_silver_bullet as sb  # noqa: E402

START_DATE, END_DATE = "2021-01-01", "2024-12-31"
SYMBOLS = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "USDCAD",
    "USA500IDXUSD",
    "USATECHIDXUSD",
    "USA30IDXUSD",
]
WINDOWS = ["AM", "PM"]


def main() -> int:
    cal_df = load_calendar_blackout_df()
    print("=" * 85)
    print("CYCLE 22: MULTI-ASSET INSTITUTIONAL SILVER BULLET UNIVERSE (2021-2024)")
    print(f"Universe: {len(SYMBOLS)} Instruments | Windows: {WINDOWS} | Period: 48 Months")
    print("=" * 85)
    
    all_trades_list = []
    summary_rows = []
    
    for sym in SYMBOLS:
        print(f"\nProcessing {sym}...")
        df_m1 = load_m1_symbol(sym)
        if df_m1.empty:
            print(f"  Warning: No data for {sym}")
            continue
        b = sb.prepare(df_m1)
        
        sym_trades = []
        for win in WINDOWS:
            t = sb.run_slot_c22(b, sym, win, START_DATE, END_DATE, cal_df)
            if not t.empty:
                t["symbol"] = sym
                t["window"] = win
                sym_trades.append(t)
                all_trades_list.append(t)
                
        if sym_trades:
            combined_sym = pd.concat(sym_trades, ignore_index=True)
            m = compute_metrics(combined_sym)
            per_month = m["n"] / 48.0
            summary_rows.append({
                "Symbol": sym,
                "Trades": m["n"],
                "Trades/Mo": round(per_month, 2),
                "WinRate%": round(m["win_rate"] * 100, 1),
                "ProfitFactor": round(m["pf"], 2),
                "MeanR": round(m["mean_r"], 3),
                "MaxDD_R": round(m["max_dd_r"], 1),
            })
            print(f"  {sym:14s}: {m['n']} trades ({per_month:.2f}/mo) | Win: {m['win_rate']*100:.1f}% | PF: {m['pf']:.2f} | MeanR: {m['mean_r']:+.3f}R | DD: {m['max_dd_r']:.1f}R")
        else:
            summary_rows.append({
                "Symbol": sym, "Trades": 0, "Trades/Mo": 0.0, "WinRate%": 0.0,
                "ProfitFactor": 0.0, "MeanR": 0.0, "MaxDD_R": 0.0,
            })
            print(f"  {sym:14s}: 0 trades")
            
    print("\n" + "=" * 85)
    print("=== SUMMARY BY ASSET (4-YEAR AGGREGATE 2021-2024) ===")
    print("=" * 85)
    summary_df = pd.DataFrame(summary_rows)
    print(summary_df.to_string(index=False))
    
    # Portfolio level metrics
    if all_trades_list:
        portfolio_trades = pd.concat(all_trades_list, ignore_index=True)
        pm = compute_metrics(portfolio_trades)
        total_monthly = pm["n"] / 48.0
        print("\n" + "=" * 85)
        print("=== PORTFOLIO TOTALS (ALL 8 INSTRUMENTS COMBINED) ===")
        print("=" * 85)
        print(f"Total Trades:           {pm['n']} trades across 48 months")
        print(f"Average Monthly Trades: {total_monthly:.2f} trades / month")
        print(f"Portfolio Win Rate:     {pm['win_rate']*100:.1f}%")
        print(f"Portfolio Profit Factor:{pm['pf']:.2f}")
        print(f"Portfolio Mean R:       {pm['mean_r']:+.3f}R per trade")
        print(f"Portfolio Max Drawdown: {pm['max_dd_r']:.1f}R")
        print("=" * 85)
        
        portfolio_trades.to_csv(REPO / "out" / "c22_multi_asset_trades.csv", index=False)
        summary_df.to_csv(REPO / "out" / "c22_multi_asset_summary.csv", index=False)
        
    return 0


if __name__ == "__main__":
    sys.exit(main())
