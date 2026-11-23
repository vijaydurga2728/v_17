"""Merged Institutional Silver Bullet (Cycle 22 + Cycle 24 Confluence).

Combines:
1. Cycle 22: Liquidity Sweep + MSS + M5 FVG entry
2. Cycle 24: H1 Order Block Tap + LTF (M5) Displacement FVG entry
Evaluated across Grade-A Curated Institutional Portfolio:
- XAUUSD (Gold)
- USA30IDXUSD (Dow 30)
- USA500IDXUSD (S&P 500)
- USATECHIDXUSD (Nasdaq 100)
- EURUSD
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df, compute_metrics
from v17.setups import c22_silver_bullet as sb
from v17.setups.c24_htf_ob_ltf_fvg import build_h1, build_m5 as build_m5_c24, ActiveOB

NY = ZoneInfo("America/New_York")

def run_merged_backtest():
    print("=" * 80, flush=True)
    print("TESTING MERGED CYCLE 22 + CYCLE 24 INSTITUTIONAL ENGINE", flush=True)
    print("=" * 80, flush=True)

    cal_df = load_calendar_blackout_df()

    symbols = ["XAUUSD", "USA30IDXUSD", "USA500IDXUSD", "USATECHIDXUSD", "EURUSD"]
    bars_cache = {}
    for s in symbols:
        print(f"Loading {s}...", flush=True)
        bars_cache[s] = sb.prepare(load_m1_symbol(s))

    # Evaluate both setups on DEV (2021-2024) and OOS (2025-2026)
    for period_name, start_d, end_d in [("DEV [2021-2024]", "2021-01-01", "2024-12-31"), ("OOS [2025-2026]", "2025-01-01", "2026-12-31")]:
        trades_list = []
        for s in symbols:
            b = bars_cache[s]
            # Cycle 22 slots
            for win in (["AM", "PM"] if s in ["EURUSD", "XAUUSD"] else ["PM"]):
                t_c22 = sb.run_slot_c22(b, s, win, start_d, end_d, cal_df)
                if not t_c22.empty:
                    t_c22["source"] = f"C22_{win}"
                    t_c22["symbol"] = s
                    trades_list.append(t_c22)
            
            # Cycle 24 HTF OB trades in NY session
            sp = sb.SPECS.get(s, sb.Spec(min_stop=0.0006, max_stop=0.0030, slip=0.00005, commission_rt=0.0))
            # Scan c24
            from v17.setups.c24_htf_ob_ltf_fvg import scan_htf_ob_ltf_fvg_trades, Spec as C24Spec
            c24_sp = C24Spec(min_stop=sp.min_stop, max_stop=sp.max_stop, slip=sp.slip, commission_rt=sp.commission_rt)
            t_c24 = scan_htf_ob_ltf_fvg_trades(
                b.ts, b.bid_o, b.bid_h, b.bid_l, b.bid_c,
                b.ask_o, b.ask_h, b.ask_l, b.ask_c,
                b.mid_o, b.mid_h, b.mid_l, b.mid_c,
                s, c24_sp, start_d, end_d, target_rr=2.0
            )
            if not t_c24.empty:
                t_c24["source"] = "C24_HTF_OB"
                t_c24["symbol"] = s
                # Standardize columns: need 'r', 'day'
                trades_list.append(t_c24)

        if not trades_list:
            print(f"No trades for {period_name}")
            continue

        df_all = pd.concat(trades_list, ignore_index=True)
        # Sort and deduplicate by (symbol, day) to honor Rule R4 & R23
        df_all["dt"] = pd.to_datetime(df_all["day"])
        df_all = df_all.sort_values("dt").drop_duplicates(subset=["symbol", "day"]).reset_index(drop=True)
        
        m = compute_metrics(df_all)
        r = df_all["r"].to_numpy(np.float64)
        sharpe = (r.mean() / r.std() * np.sqrt(252)) if len(r) > 1 and r.std() > 0 else 0.0

        print(f"\n>>> {period_name} TOTALS:", flush=True)
        print(f"    Total Trades n = {m['n']}", flush=True)
        print(f"    Win Rate       = {m['win_rate']*100:.1f}%", flush=True)
        print(f"    Profit Factor  = {m['pf']:.2f}", flush=True)
        print(f"    Mean Return    = {m['mean_r']:+.3f} R", flush=True)
        print(f"    Max Drawdown   = {m['max_dd_r']:.2f} R", flush=True)
        print(f"    Annual Sharpe  = {sharpe:.2f}", flush=True)

        # Monte Carlo
        np.random.seed(42)
        mc_pfs, mc_dds = [], []
        n_t = len(r)
        for _ in range(1000):
            sample = np.random.choice(r, size=n_t, replace=True)
            w = sample[sample > 0].sum()
            l = abs(sample[sample <= 0].sum())
            pf = w / l if l > 0 else 999.0
            mc_pfs.append(pf)
            eq = np.r_[0.0, np.cumsum(sample)]
            dd = float((np.maximum.accumulate(eq) - eq).max())
            mc_dds.append(dd)
        p5_pf = np.percentile(mc_pfs, 5)
        p95_dd = np.percentile(mc_dds, 95)
        print(f"    Monte Carlo p5(PF) = {p5_pf:.2f} (Target > 1.0)", flush=True)
        print(f"    Monte Carlo p95(DD)= {p95_dd:.2f} R (Target <= 8.0R)", flush=True)

if __name__ == "__main__":
    run_merged_backtest()
