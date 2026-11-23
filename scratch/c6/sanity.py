import pandas as pd, pyarrow.parquet as pq
from pathlib import Path
p=Path("data/bars_m5/AUDUSD/year=2022")
frames=[pq.read_table(x).to_pandas() for x in sorted(p.glob("*.parquet"))]
df=pd.concat(frames).sort_values("ts_utc")
print(df.head(3))
print("\nspread stats (ask_c - bid_c):")
s=df["ask_c"]-df["bid_c"]
print(s.describe())
print("\nany bid > ask?", (df["bid_c"]>df["ask_c"]).sum())
print("any bid_h < bid_l?", (df["bid_h"]<df["bid_l"]).sum())
print("any ask_h < ask_l?", (df["ask_h"]<df["ask_l"]).sum())
