"""Diagnose cycle 6: run 1 year, 1 config, print exit-reason + side PnL breakdown."""
import pandas as pd
from pathlib import Path
from v17.backtest.c6_runner import run_backtest
import pyarrow.parquet as pq

root = Path(r"C:/personal/v_17")
m5 = root/"data"/"bars_m5"
def load(sym):
    frames=[]
    for yr in range(2015,2024):
        d=m5/sym/f"year={yr}"
        for p in sorted(d.glob("*.parquet")):
            frames.append(pq.read_table(p).to_pandas())
    return pd.concat(frames,ignore_index=True).sort_values("ts_utc").reset_index(drop=True)

spx=load("USA500IDXUSD"); aud=load("AUDUSD"); jpy=load("USDJPY")
cal=pq.read_table(root/"data/calendar_cache/ff_c6_index.parquet").to_pandas()
# One year subset
start=pd.Timestamp("2022-01-01",tz="UTC").value
end  =pd.Timestamp("2022-12-31",tz="UTC").value
tl,ec=run_backtest(spx,{"AUDUSD":aud,"USDJPY":jpy},cal,
    params={"K":0.3,"slope_window":12,"C":0.4},initial_equity=10000.0,
    start_ts_ns=start,end_ts_ns=end)
print(f"trades={len(tl)}")
if len(tl)==0: raise SystemExit
print(f"net_pnl_total={tl['net_pnl_usd'].sum():.2f}")
print("\nBy side:")
print(tl.groupby("side")["net_pnl_usd"].agg(["count","sum","mean"]))
print("\nBy regime_at_entry:")
print(tl.groupby("regime_at_entry")["net_pnl_usd"].agg(["count","sum","mean"]))
# Exit reasons
exits_a=tl[["leg_a_reason","net_pnl_usd"]].copy()
exits_b=tl[["leg_b_reason","net_pnl_usd"]].copy()
print("\nleg_a_reason counts:"); print(tl["leg_a_reason"].value_counts())
print("\nleg_b_reason counts:"); print(tl["leg_b_reason"].value_counts())
# Expectancy per side by reason
print("\nwin rate overall:", (tl["net_pnl_usd"]>0).mean())
print("avg win:", tl[tl["net_pnl_usd"]>0]["net_pnl_usd"].mean())
print("avg loss:", tl[tl["net_pnl_usd"]<0]["net_pnl_usd"].mean())
