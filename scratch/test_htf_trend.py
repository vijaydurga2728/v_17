"""Audit: Cycle 22 London GBPUSD with HTF Daily Trend Alignment Filter.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df
from v17.setups import c22_silver_bullet as sb

START_DATE = "2021-01-01"
END_DATE = "2024-12-31"

cal_df = load_calendar_blackout_df()
m1_gbp = load_m1_symbol("GBPUSD")
b_gbp = sb.prepare(m1_gbp)

sb.WINDOWS["LDN_KZ"] = ((2, 0), (5, 0))
sb.SESSION_ENDS["LDN_KZ"] = (8, 0)
sb.SPECS["GBPUSD"] = sb.Spec(min_stop=0.0010, max_stop=0.0035, slip=0.00005, commission_rt=0.00006)

baseline_trades = sb.run_slot_c22(b_gbp, "GBPUSD", "LDN_KZ", START_DATE, END_DATE, cal_df)

# Compute Daily Trend: 20-day SMA of Daily Close (point-in-time, lagging by 1 day)
daily_bars = pd.read_parquet(REPO / "data" / "bars_d1" / "GBPUSD" / "dev" / "year=2021" / "data.parquet")
# Load all available daily bars
d_dfs = []
for p in (REPO / "data" / "bars_d1" / "GBPUSD").glob("**/*.parquet"):
    d_dfs.append(pd.read_parquet(p))
df_daily = pd.concat(d_dfs).sort_values("ts_utc").drop_duplicates("ts_utc").reset_index(drop=True)
df_daily["day"] = pd.to_datetime(df_daily["ts_utc"], unit="ns", utc=True).dt.strftime("%Y-%m-%d")
df_daily["c"] = (df_daily["bid_c"] + df_daily["ask_c"]) / 2.0
df_daily["sma20"] = df_daily["c"].rolling(20).mean()
# Lag by 1 day to ensure zero lookahead
df_daily["prev_c"] = df_daily["c"].shift(1)
df_daily["prev_sma20"] = df_daily["sma20"].shift(1)
df_daily["trend"] = np.where(df_daily["prev_c"] > df_daily["prev_sma20"], 1, -1)
trend_map = dict(zip(df_daily["day"], df_daily["trend"]))

# Evaluate trades with HTF Trend Filter
aligned_trades = []
for _, tr in baseline_trades.iterrows():
    d = str(tr["day"])
    t = trend_map.get(d, 0)
    # Trade side: +1 is Buy, -1 is Sell
    if tr["side"] == t:
        aligned_trades.append(tr)

a_df = pd.DataFrame(aligned_trades)

print("=" * 80)
print("HTF DAILY TREND FILTER ON LONDON GBPUSD (2021-2024)")
print("=" * 80)
print(f"Baseline Trades: {len(baseline_trades)} | Aligned Trades: {len(a_df)}")

b_wr = (baseline_trades["r"] > 0).mean() * 100
b_pf = baseline_trades[baseline_trades["r"] > 0]["r"].sum() / abs(baseline_trades[baseline_trades["r"] < 0]["r"].sum())
b_mean = baseline_trades["r"].mean()

a_wr = (a_df["r"] > 0).mean() * 100
a_pf = a_df[a_df["r"] > 0]["r"].sum() / abs(a_df[a_df["r"] < 0]["r"].sum())
a_mean = a_df["r"].mean()

cum_r = a_df["r"].cumsum()
dd = (cum_r.cummax() - cum_r).max()

b_cum_r = baseline_trades["r"].cumsum()
b_dd = (b_cum_r.cummax() - b_cum_r).max()

print(f"Metric             Baseline        HTF Aligned     Difference")
print(f"Win Rate:          {b_wr:.1f}%          {a_wr:.1f}%          {a_wr - b_wr:+.1f}%")
print(f"Profit Factor:     {b_pf:.2f}           {a_pf:.2f}           {a_pf - b_pf:+.2f}")
print(f"Mean Return:       {b_mean:+.3f} R       {a_mean:+.3f} R       {a_mean - b_mean:+.3f} R")
print(f"Max Drawdown:      {b_dd:.2f} R         {dd:.2f} R         {dd - b_dd:+.2f} R")
