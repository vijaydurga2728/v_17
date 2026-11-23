"""Test the core premise: does SPX regime predict FX direction on M5 at all?
No strategy wrappers. Just: given SPX regime state at bar t, what is the FX
mid-close return over next N bars? Positive expectancy in LONG_BIAS? Negative in SHORT_BIAS?"""
import pandas as pd, numpy as np, pyarrow.parquet as pq
from pathlib import Path
from v17.setups.c6_regime import compute_regime

root = Path(r"C:/personal/v_17"); m5 = root / "data" / "bars_m5"


def load(sym):
    frames = []
    for yr in range(2015, 2024):
        for p in sorted((m5 / sym / f"year={yr}").glob("*.parquet")):
            frames.append(pq.read_table(p).to_pandas())
    return pd.concat(frames, ignore_index=True).sort_values("ts_utc").reset_index(drop=True)


print("loading...")
spx = load("USA500IDXUSD"); aud = load("AUDUSD"); jpy = load("USDJPY")
reg = compute_regime(spx, k_atr=0.3, slope_window=12, session_anchor_hour=8, atr_period=14)

print("regime distribution:")
print(reg["regime_state"].value_counts(normalize=True))

for sym_name, fx in [("AUDUSD", aud), ("USDJPY", jpy)]:
    # Align FX mid closes to SPX regime timestamps via inner merge.
    fx_mid = ((fx["bid_c"] + fx["ask_c"]) * 0.5)
    fx_df = pd.DataFrame({"ts_utc": fx["ts_utc"], "mid": fx_mid})
    m = reg[["ts_utc", "regime_state"]].merge(fx_df, on="ts_utc", how="inner")
    print(f"\n=== {sym_name} merged bars: {len(m)} ===")
    # Forward returns over 1, 6, 12, 24 bars (5min, 30min, 60min, 120min)
    for horizon in (1, 6, 12, 24):
        ret = (m["mid"].shift(-horizon) / m["mid"] - 1.0) * 10000  # bps
        bias_long = m["regime_state"] == "LONG_BIAS"
        bias_short = m["regime_state"] == "SHORT_BIAS"
        bias_flat = m["regime_state"] == "FLAT"
        r_long = ret[bias_long].dropna()
        r_short = ret[bias_short].dropna()
        r_flat = ret[bias_flat].dropna()
        print(f"h={horizon:>3}  LONG n={len(r_long):>6} mean={r_long.mean():+6.2f}bps  "
              f"SHORT n={len(r_short):>6} mean={r_short.mean():+6.2f}bps  "
              f"FLAT mean={r_flat.mean():+6.2f}bps")
