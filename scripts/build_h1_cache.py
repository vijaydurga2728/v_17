"""Build H1 cache for EURUSD, GBPUSD, USATECHIDXUSD (dev + holdout).

Reads M1 paired bars from V17_BARS_ROOT (default: SB worktree), resamples
to H1 via resample_paired, writes one parquet per (symbol, partition, year).

Output layout:
  data/bars_h1/<SYMBOL>/<PARTITION>/year=YYYY/data.parquet

Idempotent: overwrites existing partitions.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.common.types import TF
from v17.data.parquet_store import read_bars
from v17.data.resample import resample_paired


SYMBOLS = ("EURUSD", "GBPUSD", "USATECHIDXUSD")
PARTITIONS = ("dev", "holdout")


def _bars_root() -> Path:
    env = os.environ.get("V17_BARS_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / ".worktrees" / "sb-6-engine-gate" / "data"


def main() -> None:
    bars_root = _bars_root()
    out_root = Path("data/bars_h1")
    out_root.mkdir(parents=True, exist_ok=True)

    totals: dict = {}
    for sym in SYMBOLS:
        for part in PARTITIONS:
            dev_only = part == "dev"
            print(f"[h1-build] loading {sym} {part} M1 from {bars_root}", flush=True)
            m1 = read_bars(root=bars_root, symbol=sym, partition=part, dev_only=dev_only)
            if m1.empty:
                print(f"[h1-build] no M1 bars for {sym} {part}; skip", flush=True)
                continue
            print(f"[h1-build] M1 rows: {len(m1):,}", flush=True)
            h1 = resample_paired(m1, TF.H1)
            print(f"[h1-build] H1 rows: {len(h1):,}", flush=True)

            # Partition by year.
            year_series = pd.to_datetime(h1["ts_utc"], unit="ns", utc=True).dt.year
            for year_val, chunk in h1.groupby(year_series):
                out_dir = out_root / sym / part / f"year={int(year_val)}"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / "data.parquet"
                pq.write_table(pa.Table.from_pandas(chunk, preserve_index=False), out_path)
                print(f"[h1-build]   wrote {out_path} ({len(chunk)} rows)", flush=True)
            totals[(sym, part)] = len(h1)

    print(f"[h1-build] DONE. Totals: {totals}", flush=True)


if __name__ == "__main__":
    main()
