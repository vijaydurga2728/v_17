"""Ingest Dukascopy M1 Ask+Bid CSVs for FX majors into paired-bar parquet.

Reads from: C:/Users/Vijayakumar R/Documents/<SYMBOL>_1 Min_<Ask|Bid>_<DATES>.csv
Writes to:  .worktrees/sb-6-engine-gate/data/bars/<SYMBOL>/{dev,holdout}/year=YYYY/month=MM/data.parquet

Dev partition: ts < 2025-01-01 UTC.
Holdout partition: 2025-01-01 <= ts < future.

Dukascopy CSVs use EET (Eastern European Time). Converted to UTC.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


DOCS = Path("C:/Users/Vijayakumar R/Documents")
OUT_ROOT = Path(".worktrees/sb-6-engine-gate/data/bars")
SYMBOLS = ("AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY", "EURGBP")
# EET = UTC+2 (winter) / UTC+3 (summer). We treat as UTC+2 constant for simplicity;
# this is a 1-hour approximation during DST periods (~7 months of the year).
# TODO: proper EET->UTC conversion if sub-hour alignment matters for signal.
EET_OFFSET_HOURS = 2
DEV_CUTOFF_UTC_NS = pd.Timestamp("2025-01-01", tz="UTC").value


def _parse_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, header=0, names=["ts_eet", "o", "h", "l", "c", "v"],
                     skiprows=1, dtype={"o": float, "h": float, "l": float, "c": float, "v": float})
    # Convert EET -> UTC (EET = UTC+2 approx)
    df["ts_utc"] = pd.to_datetime(df["ts_eet"], format="%Y.%m.%d %H:%M:%S", utc=False)
    df["ts_utc"] = (df["ts_utc"] - pd.Timedelta(hours=EET_OFFSET_HOURS)).dt.tz_localize("UTC")
    df["ts_utc"] = df["ts_utc"].astype("int64")
    return df[["ts_utc", "o", "h", "l", "c", "v"]]


def _find_csvs(symbol: str, side: str) -> list[Path]:
    pattern = re.compile(rf"^{re.escape(symbol)}_1 Min_{side}_\d{{4}}\.\d{{2}}\.\d{{2}}_\d{{4}}\.\d{{2}}\.\d{{2}}\.csv$")
    return sorted([p for p in DOCS.iterdir() if pattern.match(p.name)])


def ingest_symbol(symbol: str) -> None:
    ask_csvs = _find_csvs(symbol, "Ask")
    bid_csvs = _find_csvs(symbol, "Bid")
    if not ask_csvs or not bid_csvs:
        print(f"[ingest] {symbol}: missing CSVs ask={len(ask_csvs)} bid={len(bid_csvs)}")
        return

    ask_df = pd.concat([_parse_csv(p) for p in ask_csvs], ignore_index=True)
    ask_df = ask_df.drop_duplicates("ts_utc").sort_values("ts_utc").reset_index(drop=True)
    bid_df = pd.concat([_parse_csv(p) for p in bid_csvs], ignore_index=True)
    bid_df = bid_df.drop_duplicates("ts_utc").sort_values("ts_utc").reset_index(drop=True)

    paired = pd.merge(
        ask_df.rename(columns={"o": "ask_o", "h": "ask_h", "l": "ask_l", "c": "ask_c", "v": "ask_volume"}),
        bid_df.rename(columns={"o": "bid_o", "h": "bid_h", "l": "bid_l", "c": "bid_c", "v": "bid_volume"}),
        on="ts_utc", how="inner",
    )
    paired["symbol"] = symbol
    paired["spread_mid"] = paired["ask_c"] - paired["bid_c"]

    cols = ["ts_utc", "symbol", "bid_o", "bid_h", "bid_l", "bid_c",
            "ask_o", "ask_h", "ask_l", "ask_c", "bid_volume", "ask_volume", "spread_mid"]
    paired = paired[cols]
    print(f"[ingest] {symbol}: {len(paired):,} paired M1 bars  (ask={len(ask_df):,} bid={len(bid_df):,})")

    # Partition by dev/holdout + year/month.
    dev = paired[paired["ts_utc"] < DEV_CUTOFF_UTC_NS].copy()
    holdout = paired[paired["ts_utc"] >= DEV_CUTOFF_UTC_NS].copy()

    for part_name, part_df in [("dev", dev), ("holdout", holdout)]:
        if part_df.empty:
            continue
        dt = pd.to_datetime(part_df["ts_utc"], unit="ns", utc=True)
        part_df["_year"] = dt.dt.year
        part_df["_month"] = dt.dt.month
        for (year, month), chunk in part_df.groupby(["_year", "_month"]):
            out_dir = OUT_ROOT / symbol / part_name / f"year={int(year)}" / f"month={int(month):02d}"
            out_dir.mkdir(parents=True, exist_ok=True)
            payload = chunk.drop(columns=["_year", "_month"])
            pq.write_table(pa.Table.from_pandas(payload, preserve_index=False), out_dir / "data.parquet")
        print(f"[ingest]   wrote {part_name}: {len(part_df):,} rows")


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for sym in SYMBOLS:
        if only and sym != only:
            continue
        print(f"\n=== {sym} ===", flush=True)
        try:
            ingest_symbol(sym)
        except Exception as exc:
            print(f"[ingest] {sym} FAILED: {exc}", flush=True)


if __name__ == "__main__":
    main()
