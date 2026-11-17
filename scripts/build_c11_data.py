"""Cycle 11 data: ingest US30 paired M1 (if missing) and build UTC-day D1 for SPX and US30.

D1 construction is identical to scripts/build_d1_cache.py (cycle 4B NAS100):
``resample_paired(m1, TF.D1)`` on UTC days. Partitions: dev = years <= 2024, holdout = 2025+.
Only writes data/bars_m1_paired/USA30IDXUSD/ and data/bars_d1/{USA500IDXUSD,USA30IDXUSD}/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from v17.common.types import TF  # noqa: E402
from v17.data.c6_pipeline import ingest_m1_paired  # noqa: E402
from v17.data.resample import resample_paired  # noqa: E402

CSV_DIR = Path("C:/Users/Vijayakumar R/Documents")
M1_ROOT = REPO / "data" / "bars_m1_paired"
D1_ROOT = REPO / "data" / "bars_d1"
SYMBOLS = ("USA500IDXUSD", "USA30IDXUSD")
HOLDOUT_FIRST_YEAR = 2025


def ensure_us30_m1() -> None:
    if (M1_ROOT / "USA30IDXUSD").exists():
        print("[c11-data] US30 M1 already ingested")
        return
    bid = CSV_DIR / "USA30IDXUSD_1 Min_Bid_2015.01.01_2026.10.14.csv"
    ask = CSV_DIR / "USA30IDXUSD_1 Min_Ask_2015.01.01_2026.10.14.csv"
    n = ingest_m1_paired(bid, ask, "USA30IDXUSD", M1_ROOT)
    print(f"[c11-data] ingested US30 M1 rows: {n:,}")


def build_d1(symbol: str) -> None:
    m1 = pd.read_parquet(M1_ROOT / symbol).sort_values("ts_utc").reset_index(drop=True)
    m1 = m1.drop_duplicates("ts_utc")
    print(f"[c11-data] {symbol} M1 rows {len(m1):,}")
    d1 = resample_paired(m1, TF.D1)
    years = pd.to_datetime(d1["ts_utc"], unit="ns", utc=True).dt.year
    for year, chunk in d1.groupby(years):
        part = "holdout" if int(year) >= HOLDOUT_FIRST_YEAR else "dev"
        out = D1_ROOT / symbol / part / f"year={int(year)}" / "data.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(chunk, preserve_index=False), out)
    print(f"[c11-data] {symbol} D1 rows {len(d1):,} "
          f"({pd.to_datetime(d1.ts_utc.iloc[0], unit='ns').date()} -> "
          f"{pd.to_datetime(d1.ts_utc.iloc[-1], unit='ns').date()})")


def main() -> int:
    ensure_us30_m1()
    for s in SYMBOLS:
        build_d1(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
