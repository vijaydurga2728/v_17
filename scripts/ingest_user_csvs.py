"""Batch ingest user's Documents CSVs into parquet. Reads v17.config.Settings
`dukascopy_csv_dir` or defaults to the user's Documents folder.
"""
from __future__ import annotations

import sys
from pathlib import Path

from v17.common.types import Symbol
from v17.config import get_settings
from v17.data.dukascopy_csv import stitch_pair
from v17.data.parquet_store import write_1m

USER_CSV_DIR = Path("C:/Users/Vijayakumar R/Documents")

# Tier 1 priority symbols for FTMO expansion. User-approved.
TIER_1 = ["EURGBP", "USATECHIDXUSD"]  # NAS100 = USATECHIDXUSD per Dukascopy
# Tier 2 if Tier 1 ingest clean + edge measured
TIER_2 = ["USDJPY", "AUDUSD"]
# Tier 3 lower priority
TIER_3 = ["USDCAD", "USDCHF", "NZDUSD", "USA500IDXUSD", "USA30IDXUSD"]


def ingest_one(symbol: str, csv_dir: Path, parquet_root: Path) -> int:
    bids = sorted(csv_dir.glob(f"{symbol}_1 Min_Bid_*.csv"))
    asks = sorted(csv_dir.glob(f"{symbol}_1 Min_Ask_*.csv"))
    if not bids or not asks:
        print(f"[{symbol}] SKIP: no bid+ask CSVs")
        return 0
    print(f"[{symbol}] stitching bid={len(bids)} ask={len(asks)}")
    df = stitch_pair(bids, asks, symbol=symbol)
    write_1m(df, Symbol(symbol), parquet_root)
    print(f"[{symbol}] wrote {len(df):,} rows")
    return len(df)


def main() -> int:
    s = get_settings()
    s.ensure_dirs()
    csv_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else USER_CSV_DIR
    symbols = sys.argv[2:] if len(sys.argv) > 2 else TIER_1
    print(f"csv_dir: {csv_dir}")
    print(f"parquet_root: {s.parquet_root}")
    print(f"symbols: {symbols}")
    print()
    total = 0
    for sym in symbols:
        total += ingest_one(sym, csv_dir, s.parquet_root)
    print(f"\ndone. total rows: {total:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
