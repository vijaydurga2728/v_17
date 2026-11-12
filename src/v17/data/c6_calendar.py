"""Cycle 6 ForexFactory calendar cache + blackout lookup."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dateutil import parser as dateparser

_IMPACT_MAP = {"High": "high", "Medium": "medium", "Low": "low"}


def build_calendar_index(
    ff_dir: Path, out_parquet: Path, currencies: tuple[str, ...]
) -> int:
    rows = []
    for p in sorted(ff_dir.glob("*.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))
        for item in raw:
            impact = _IMPACT_MAP.get(item.get("impact", ""))
            if impact != "high":
                continue
            cur = item.get("country")
            if cur not in currencies:
                continue
            ts = dateparser.isoparse(item["date"])
            rows.append({
                "ts_utc": pd.Timestamp(ts).tz_convert("UTC").value,
                "currency": cur,
                "impact": impact,
                "title": item.get("title", ""),
            })
    df = pd.DataFrame(rows).drop_duplicates(subset=["ts_utc", "currency", "title"])
    df = df.sort_values("ts_utc").reset_index(drop=True)
    schema = pa.schema([
        ("ts_utc", pa.int64()),
        ("currency", pa.string()),
        ("impact", pa.string()),
        ("title", pa.string()),
    ])
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, schema=schema, preserve_index=False),
                   out_parquet, compression="zstd")
    return len(df)


def load_calendar_index(index_parquet: Path) -> pd.DataFrame:
    return pq.read_table(index_parquet).to_pandas().sort_values("ts_utc").reset_index(drop=True)


def is_blackout(ts_utc_ns: int, index: pd.DataFrame, blackout_min: int) -> bool:
    if index.empty:
        return False
    delta_ns = blackout_min * 60 * 1_000_000_000
    return bool(((index["ts_utc"] - ts_utc_ns).abs() <= delta_ns).any())


def is_calendar_stale(sim_ts_ns: int, index: pd.DataFrame, max_age_hours: int = 48) -> bool:
    if index.empty:
        return True
    max_event = int(index["ts_utc"].max())
    return (sim_ts_ns - max_event) > max_age_hours * 3600 * 1_000_000_000
