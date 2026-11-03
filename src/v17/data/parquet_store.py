from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from v17.common.paths import parquet_file
from v17.common.types import TF, Symbol

_SCHEMA_1M = pa.schema(
    [
        ("ts", pa.timestamp("us", tz="UTC")),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.int64()),
        ("spread_pips", pa.float64()),
    ]
)


def write_1m(df: pd.DataFrame, symbol: Symbol, parquet_root: Path) -> None:
    df = df.copy()
    df["year"] = df["ts"].dt.year
    for year_val, chunk in df.groupby("year"):
        out = parquet_file(parquet_root, symbol, TF.M1, int(str(year_val)))
        out.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(
            chunk.drop(columns=["year"]), schema=_SCHEMA_1M, preserve_index=False
        )
        pq.write_table(table, out, compression="zstd")


def read_1m(
    symbol: Symbol, start: datetime, end: datetime, parquet_root: Path
) -> pd.DataFrame:
    years = range(start.year, end.year + 1)
    frames: list[pd.DataFrame] = []
    for y in years:
        p = parquet_file(parquet_root, symbol, TF.M1, y)
        if p.exists():
            frames.append(pq.read_table(p).to_pandas())
    if not frames:
        return pd.DataFrame(columns=[f.name for f in _SCHEMA_1M])
    df = pd.concat(frames, ignore_index=True)
    mask = (df["ts"] >= pd.Timestamp(start)) & (df["ts"] <= pd.Timestamp(end))
    return df.loc[mask].sort_values("ts").reset_index(drop=True)


from v17.data.partition_guard import HOLDOUT_START_UTC_NS, assert_dev_only


def _partition_of(ts_ns: int) -> str:
    return "holdout" if ts_ns >= HOLDOUT_START_UTC_NS else "dev"


def write_bars_partitioned(df: pd.DataFrame, root: Path) -> None:
    df = df.copy()
    df["_partition"] = df["ts_utc"].map(_partition_of)
    ts = pd.to_datetime(df["ts_utc"], utc=True)
    df["_year"] = ts.dt.year
    df["_month"] = ts.dt.month
    for (symbol, part, year, month), group in df.groupby(["symbol", "_partition", "_year", "_month"]):
        out_dir = Path(root) / "bars" / symbol / part / f"year={year}" / f"month={month:02d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = group.drop(columns=["_partition", "_year", "_month"])
        pq.write_table(pa.Table.from_pandas(payload), out_dir / "data.parquet")


def read_bars(root: Path, symbol: str, partition: str = "dev", dev_only: bool = True) -> pd.DataFrame:
    if dev_only:
        assert_dev_only(partition)
    base = Path(root) / "bars" / symbol / partition
    if not base.exists():
        return pd.DataFrame()
    files = list(base.rglob("data.parquet"))
    if not files:
        return pd.DataFrame()
    tables = [pq.read_table(f) for f in files]
    return pa.concat_tables(tables).to_pandas()
