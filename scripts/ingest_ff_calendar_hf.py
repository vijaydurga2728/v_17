"""Download Ehsanrs2/Forex_Factory_Calendar HuggingFace dataset, filter to
USD/EUR/GBP High-impact events for 2021-2024, write as v17 JSON archive.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

CSV_URL = (
    "https://huggingface.co/datasets/"
    "Ehsanrs2/Forex_Factory_Calendar/resolve/main/forex_factory_cache.csv"
)
ALLOWED_CURRENCIES = {"USD", "EUR", "GBP"}
HIGH_IMPACT = {"High Impact Expected"}
START = datetime(2021, 1, 1, tzinfo=UTC)
END = datetime(2025, 1, 1, tzinfo=UTC)


def main(out_path: Path) -> int:
    print(f"[1/4] downloading {CSV_URL}", file=sys.stderr)
    df = pd.read_csv(CSV_URL, dtype=str)
    print(f"[2/4] rows loaded: {len(df):,}", file=sys.stderr)

    df["DateTime"] = pd.to_datetime(df["DateTime"], utc=True, errors="coerce")
    df = df.dropna(subset=["DateTime"])
    df = df[(df["DateTime"] >= START) & (df["DateTime"] < END)]
    df = df[df["Currency"].isin(ALLOWED_CURRENCIES)]
    df = df[df["Impact"].isin(HIGH_IMPACT)]
    print(f"[3/4] rows kept (2021-2024, USD/EUR/GBP, high): {len(df):,}", file=sys.stderr)

    records = [
        {
            "date": row["DateTime"].isoformat(),
            "country": row["Currency"],
            "impact": "High",
            "title": row.get("Event") or "",
        }
        for _, row in df.iterrows()
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"[4/4] wrote {len(records):,} events to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/calendar/ff_2021_2024.json")
    sys.exit(main(out))
