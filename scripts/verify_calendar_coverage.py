import pandas as pd
df = pd.read_parquet("data/calendar/economic_events.parquet")
df["ts"] = pd.to_datetime(df["timestamp_utc"], utc=True)
by_year = df.groupby(df["ts"].dt.year).size()
print(by_year)
# Soft check: expect >50 high-impact events per year post-2015
import sys
weak_years = [y for y in by_year.index if 2015 <= y <= 2025 and by_year.loc[y] < 50]
if weak_years:
    print(f"WARN: low coverage years: {weak_years}", file=sys.stderr)
    sys.exit(2)
print("coverage OK")
