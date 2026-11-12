"""Cycle 6 data pipeline: M1 bid/ask CSV -> paired M1 parquet -> M5 parquet."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from v17.data.dukascopy_csv import read_file


_PAIRED_SCHEMA = pa.schema([
    ("ts_utc", pa.int64()),
    ("symbol", pa.string()),
    ("bid_o", pa.float64()),
    ("bid_h", pa.float64()),
    ("bid_l", pa.float64()),
    ("bid_c", pa.float64()),
    ("ask_o", pa.float64()),
    ("ask_h", pa.float64()),
    ("ask_l", pa.float64()),
    ("ask_c", pa.float64()),
    ("bid_volume", pa.int64()),
    ("ask_volume", pa.int64()),
    ("spread_mid", pa.float64()),
])


def ingest_m1_paired(
    bid_csv: Path,
    ask_csv: Path,
    symbol: str,
    out_root: Path,
) -> int:
    """Read bid and ask M1 CSVs, merge on ts, write paired parquet.

    Returns the total number of rows written.
    """
    # read_file returns columns: ts, open_{side}, high_{side}, low_{side}, close_{side}, volume
    bid = read_file(bid_csv, side="bid").rename(columns={
        "open_bid": "bid_o", "high_bid": "bid_h", "low_bid": "bid_l", "close_bid": "bid_c",
        "volume": "bid_volume",
    })
    ask = read_file(ask_csv, side="ask").rename(columns={
        "open_ask": "ask_o", "high_ask": "ask_h", "low_ask": "ask_l", "close_ask": "ask_c",
        "volume": "ask_volume",
    })

    merged = pd.merge(
        bid[["ts", "bid_o", "bid_h", "bid_l", "bid_c", "bid_volume"]],
        ask[["ts", "ask_o", "ask_h", "ask_l", "ask_c", "ask_volume"]],
        on="ts",
        how="inner",
    )

    # ts is tz-aware UTC; convert to int64 nanoseconds
    try:
        merged["ts_utc"] = merged["ts"].astype("int64")
    except Exception:
        merged["ts_utc"] = merged["ts"].astype("datetime64[ns, UTC]").astype("int64")

    merged["symbol"] = symbol
    merged["spread_mid"] = merged["ask_c"] - merged["bid_c"]

    # Cast volumes to int64 to match schema
    merged["bid_volume"] = merged["bid_volume"].astype("int64")
    merged["ask_volume"] = merged["ask_volume"].astype("int64")

    merged = merged.drop(columns=["ts"])
    merged = merged[[
        "ts_utc", "symbol",
        "bid_o", "bid_h", "bid_l", "bid_c",
        "ask_o", "ask_h", "ask_l", "ask_c",
        "bid_volume", "ask_volume", "spread_mid",
    ]]

    total = 0
    merged["year"] = pd.to_datetime(merged["ts_utc"], unit="ns", utc=True).dt.year
    for year_val, chunk in merged.groupby("year"):
        out = out_root / symbol / f"year={int(year_val)}" / "part-00.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(
            chunk.drop(columns=["year"]), schema=_PAIRED_SCHEMA, preserve_index=False
        )
        pq.write_table(table, out, compression="zstd")
        total += len(chunk)
    return total
