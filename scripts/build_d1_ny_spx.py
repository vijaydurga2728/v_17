"""Build SPX D1 bars aligned to NY local day (00:00-23:59 ET) from M1 paired.

Input:  data/bars_m1_paired/USA500IDXUSD/year=YYYY/*.parquet
Output: data/bars_d1_ny/USA500IDXUSD/year=YYYY/data.parquet

Output schema (one row per NY calendar date with any M1 data):
  ny_date       (date, string YYYY-MM-DD)
  ts_utc        (int64 ns, first bar of the NY day in UTC — informational)
  symbol        str
  bid_o, bid_h, bid_l, bid_c
  ask_o, ask_h, ask_l, ask_c
  mid_o, mid_h, mid_l, mid_c
  bid_volume    int64
  ask_volume    int64
  n_m1_bars     int64

Idempotent: overwrites existing partitions. Only touches
data/bars_d1_ny/USA500IDXUSD/.
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
OUT_ROOT = Path("data/bars_d1_ny")


def _load_year(year: int) -> pd.DataFrame:
    part_dir = SRC_ROOT / SYMBOL / f"year={year}"
    if not part_dir.exists():
        return pd.DataFrame()
    df = pd.read_parquet(part_dir)
    if df.empty:
        return df
    df["_ts_ny"] = pd.to_datetime(df["ts_utc"], unit="ns", utc=True).dt.tz_convert(TZ)
    df["ny_date"] = df["_ts_ny"].dt.strftime("%Y-%m-%d")
    return df


def _aggregate(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("ts_utc")
    g = df.groupby("ny_date", sort=True, as_index=False)
    out = g.agg(
        ts_utc=("ts_utc", "first"),
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
    out["mid_o"] = (out["bid_o"] + out["ask_o"]) / 2.0
    out["mid_h"] = (out["bid_h"] + out["ask_h"]) / 2.0
    out["mid_l"] = (out["bid_l"] + out["ask_l"]) / 2.0
    out["mid_c"] = (out["bid_c"] + out["ask_c"]) / 2.0
    return out


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    years = sorted(int(p.name.split("=")[1]) for p in (SRC_ROOT / SYMBOL).glob("year=*"))
    if not years:
        print(f"[d1-ny-build] no M1 partitions under {SRC_ROOT / SYMBOL}", flush=True)
        return 1
    totals: dict[int, int] = {}
    carry: pd.DataFrame | None = None
    for i, year in enumerate(years):
        print(f"[d1-ny-build] loading {SYMBOL} year={year}", flush=True)
        cur = _load_year(year)
        if cur.empty:
            print(f"[d1-ny-build]   empty; skip", flush=True)
            continue
        # NY-day may span prior UTC year (ET = UTC-4/-5). Pull in next-year head
        # if its NY date equals last cur NY date, to avoid split days. We stream
        # per-year and only emit bars whose NY date lies fully in `year`.
        next_year = years[i + 1] if i + 1 < len(years) else None
        if next_year is not None:
            nxt = _load_year(next_year)
            if not nxt.empty:
                cur_last_ny = cur["ny_date"].max()
                head = nxt[nxt["ny_date"] == cur_last_ny]
                if not head.empty:
                    cur = pd.concat([cur, head], ignore_index=True)
        if carry is not None and not carry.empty:
            cur = pd.concat([carry, cur], ignore_index=True)
            carry = None
        agg = _aggregate(cur)
        agg = agg[agg["ny_date"].str.startswith(f"{year}-")]
        out_dir = OUT_ROOT / SYMBOL / f"year={year}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "data.parquet"
        pq.write_table(pa.Table.from_pandas(agg, preserve_index=False), out_path)
        totals[year] = len(agg)
        print(f"[d1-ny-build]   wrote {out_path} ({len(agg)} NY days)", flush=True)
    print(f"[d1-ny-build] DONE. Rows per year: {totals}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
