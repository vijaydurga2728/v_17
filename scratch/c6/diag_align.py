"""Check SPX M5 vs FX M5 timestamp alignment and SPX data quality."""
import pandas as pd, pyarrow.parquet as pq
from pathlib import Path

root = Path(r"C:/personal/v_17"); m5 = root / "data" / "bars_m5"


def load_year(sym, yr):
    frames = [pq.read_table(p).to_pandas() for p in sorted((m5 / sym / f"year={yr}").glob("*.parquet"))]
    return pd.concat(frames, ignore_index=True).sort_values("ts_utc").reset_index(drop=True)


spx = load_year("USA500IDXUSD", 2022)
aud = load_year("AUDUSD", 2022)
jpy = load_year("USDJPY", 2022)

print(f"SPX 2022 bars: {len(spx)}")
print(f"AUDUSD 2022 bars: {len(aud)}")
print(f"USDJPY 2022 bars: {len(jpy)}")

# Intersection
spx_set = set(spx["ts_utc"].tolist())
aud_set = set(aud["ts_utc"].tolist())
jpy_set = set(jpy["ts_utc"].tolist())
inter = spx_set & aud_set & jpy_set
print(f"Intersection bars: {len(inter)}")
print(f"SPX only (not in all three): {len(spx_set - inter)}")
print(f"AUDUSD only: {len(aud_set - spx_set)}")

# SPX sanity
print("\nSPX head (bid/ask):")
print(spx[["ts_utc", "bid_o", "bid_c", "ask_o", "ask_c", "bid_volume"]].head(5))
print("\nSPX sanity: zero-volume bars:", (spx["bid_volume"] == 0).sum(), "/", len(spx))
print("SPX negative spread rows:", (spx["ask_c"] < spx["bid_c"]).sum())
print("SPX median spread (ask_c-bid_c):", (spx["ask_c"] - spx["bid_c"]).median())

# Session hours spread (SPX has cash + after-hours)
spx_ts = pd.to_datetime(spx["ts_utc"], unit="ns", utc=True)
hours = spx_ts.dt.hour.value_counts().sort_index()
print("\nSPX bars by UTC hour:")
print(hours)
