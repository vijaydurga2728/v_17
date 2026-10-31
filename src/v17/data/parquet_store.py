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
