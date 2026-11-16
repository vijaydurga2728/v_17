"""Build SPX D1 bars aligned to NY Regular Trading Hours (09:30-16:00 ET).

Open bar  = first M1 at 09:30 ET (session open).
Close bar = last M1 at or before 15:59 ET (session close prints at 16:00 ET open of next bar).
Window = [09:30, 16:00) ET local.

Input:  data/bars_m1_paired/USA500IDXUSD/year=YYYY/*.parquet
Output: data/bars_d1_rth/USA500IDXUSD/year=YYYY/data.parquet

Output schema:
  ny_date       (str YYYY-MM-DD)
  ts_utc_open   (int64 ns, first bar of the session in UTC)
  ts_utc_close  (int64 ns, last bar of the session in UTC)
  symbol        str
  bid_o, bid_h, bid_l, bid_c
  ask_o, ask_h, ask_l, ask_c
  mid_o, mid_h, mid_l, mid_c
  bid_volume, ask_volume  int64
  n_m1_bars     int64

Drops NY dates with < MIN_BARS_PER_DAY (incomplete sessions — holidays / early close).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


SYMBOL = "USA500IDXUSD"
TZ = "America/New_York"
SRC_ROOT = Path("data/bars_m1_paired")
OUT_ROOT = Path("data/bars_d1_rth")

RTH_START_MINUTES = 9 * 60 + 30  # 09:30 ET
RTH_END_MINUTES = 16 * 60        # 16:00 ET (exclusive)
MIN_BARS_PER_DAY = 60             # at least 60 M1 bars to count a session


def _load_year(year: int) -> pd.DataFrame:
    part_dir = SRC_ROOT / SYMBOL / f"year={year}"
    if not part_dir.exists():
        return pd.DataFrame()
    df = pd.read_parquet(part_dir)
    if df.empty:
        return df
    ts_ny = pd.to_datetime(df["ts_utc"], unit="ns", utc=True).dt.tz_convert(TZ)
    df["ny_date"] = ts_ny.dt.strftime("%Y-%m-%d")
    df["_min_of_day"] = ts_ny.dt.hour * 60 + ts_ny.dt.minute
    mask = (df["_min_of_day"] >= RTH_START_MINUTES) & (df["_min_of_day"] < RTH_END_MINUTES)
    return df.loc[mask].copy()


def _aggregate(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("ts_utc")
    g = df.groupby("ny_date", sort=True, as_index=False)
    out = g.agg(
        ts_utc_open=("ts_utc", "first"),
        ts_utc_close=("ts_utc", "last"),
        symbol=("symbol", "first"),
        bid_o=("bid_o", "first"),
        bid_h=("bid_h", "max"),
        bid_l=("bid_l", "min"),
        bid_c=("bid_c", "last"),
        ask_o=("ask_o", "first"),
        ask_h=("ask_h", "max"),
        ask_l=("ask_l", "min"),
        ask_c=("ask_c", "last"),
        bid_volume=("bid_volume", "sum"),
        ask_volume=("ask_volume", "sum"),
        n_m1_bars=("ts_utc", "count"),
    )
    out = out[out["n_m1_bars"] >= MIN_BARS_PER_DAY].copy()
    out["mid_o"] = (out["bid_o"] + out["ask_o"]) / 2.0
    out["mid_h"] = (out["bid_h"] + out["ask_h"]) / 2.0
    out["mid_l"] = (out["bid_l"] + out["ask_l"]) / 2.0
    out["mid_c"] = (out["bid_c"] + out["ask_c"]) / 2.0
    return out


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    years = sorted(int(p.name.split("=")[1]) for p in (SRC_ROOT / SYMBOL).glob("year=*"))
    if not years:
        print(f"[d1-rth-build] no M1 partitions under {SRC_ROOT / SYMBOL}", flush=True)
        return 1
    totals: dict[int, int] = {}
    for year in years:
        print(f"[d1-rth-build] loading {SYMBOL} year={year}", flush=True)
        cur = _load_year(year)
        if cur.empty:
            print(f"[d1-rth-build]   no RTH bars; skip", flush=True)
            continue
        agg = _aggregate(cur)
        agg = agg[agg["ny_date"].str.startswith(f"{year}-")]
        out_dir = OUT_ROOT / SYMBOL / f"year={year}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "data.parquet"
        pq.write_table(pa.Table.from_pandas(agg, preserve_index=False), out_path)
        totals[year] = len(agg)
        print(f"[d1-rth-build]   wrote {out_path} ({len(agg)} RTH days)", flush=True)
    print(f"[d1-rth-build] DONE. Rows per year: {totals}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
