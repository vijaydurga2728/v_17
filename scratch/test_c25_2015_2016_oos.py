"""Cycle 25: 2015-2016 Blind Out-of-Sample Backtest.

Tests the upgraded Cycle 25 Institutional Engine on historical 2015-2016 data:
- US Cash Open Drive (09:30 - 10:30 NY): USTEC, USA30, USA500
- NY PM Session (14:00 - 15:00 NY): USA30, USA500
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df, compute_metrics
from v17.setups import c25_silver_bullet_institutional as c25

cal_df = load_calendar_blackout_df()

START_DATE = "2015-01-01"
END_DATE = "2016-12-31"

SLOTS = [
    ("OPEN_DRIVE", "USATECHIDXUSD"),
    ("OPEN_DRIVE", "USA30IDXUSD"),
    ("OPEN_DRIVE", "USA500IDXUSD"),
    ("PM", "USA30IDXUSD"),
    ("PM", "USA500IDXUSD"),
]

symbols = sorted(list({s for _, s in SLOTS}))
bars_cache = {}

print("=" * 80, flush=True)
print(f"CYCLE 25: 2015-2016 BLIND OUT-OF-SAMPLE AUDIT [{START_DATE} to {END_DATE}]", flush=True)
print("=" * 80, flush=True)

for sym in symbols:
    print(f"Loading {sym}...", flush=True)
    bars_cache[sym] = c25.prepare(load_m1_symbol(sym))
    print(f"  {sym}: {len(bars_cache[sym].ts):,} M1 bars ready.", flush=True)

all_trades = []

print("\n" + "=" * 80, flush=True)
print(f"INDIVIDUAL SLOT PERFORMANCE ({START_DATE} to {END_DATE})", flush=True)
print("=" * 80, flush=True)

for win, sym in SLOTS:
    b = bars_cache[sym]
    t = c25.run_slot_c25(b, sym, win, START_DATE, END_DATE, cal_df)
    m = compute_metrics(t)
    
    print(f"[{win:10s}] {sym:14s} | n={m['n']:3d} | WR={m['win_rate']*100:4.1f}% | PF={m['pf']:5.2f} | MeanR={m['mean_r']:+6.3f}R | DD={m['max_dd_r']:4.1f}R", flush=True)
    
    if not t.empty:
        t["slot"] = f"{sym}_{win}"
        all_trades.append(t)

if all_trades:
    df = pd.concat(all_trades, ignore_index=True)
    df["dt"] = pd.to_datetime(df["day"])
    df = df.sort_values("dt").drop_duplicates(subset=["symbol", "day"]).reset_index(drop=True)
    
    m_tot = compute_metrics(df)
    r = df["r"].to_numpy(np.float64)
    sharpe = (r.mean() / r.std() * np.sqrt(252)) if len(r) > 1 and r.std() > 0 else 0.0
    
    print("\n" + "=" * 80, flush=True)
    print(f"2015-2016 PORTFOLIO AGGREGATE RESULTS ({START_DATE} to {END_DATE})", flush=True)
    print("=" * 80, flush=True)
    print(f"Total Trades n = {m_tot['n']}", flush=True)
    print(f"Win Rate       = {m_tot['win_rate']*100:.1f}%", flush=True)
    print(f"Profit Factor  = {m_tot['pf']:.2f}", flush=True)
    print(f"Mean Return    = {m_tot['mean_r']:+.3f} R", flush=True)
    print(f"Max Drawdown   = {m_tot['max_dd_r']:.2f} R", flush=True)
    print(f"Annual Sharpe  = {sharpe:.2f}", flush=True)
    
    # Yearly breakdown
    for yr in ["2015", "2016"]:
        sub_yr = df[df["day"].str.startswith(yr)]
        m_yr = compute_metrics(sub_yr)
        print(f"  Year {yr}: n={m_yr['n']:3d} | WR={m_yr['win_rate']*100:4.1f}% | PF={m_yr['pf']:5.2f} | MeanR={m_yr['mean_r']:+6.3f}R | DD={m_yr['max_dd_r']:4.1f}R", flush=True)
        
    # Monte Carlo 1,000 runs
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
    print(f"\nMonte Carlo 1,000 Permutations (2015-2016 OOS):", flush=True)
    print(f"  5th-percentile PF:  {p5_pf:.2f} (Target > 1.0)", flush=True)
    print(f"  Median PF:          {np.median(mc_pfs):.2f}", flush=True)
    print(f"  95th-percentile DD: {p95_dd:.2f} R", flush=True)
    print("=" * 80, flush=True)
else:
    print("No trades generated for 2015-2016.")
