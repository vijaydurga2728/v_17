"""Iterate Finnhub calendar in monthly chunks 2015-01 to 2026-10 and persist.

Requires env var FINNHUB_API_KEY set. Writes:
  data/calendar/economic_events.parquet (int64 ns timestamps)

Finnhub free tier: 60 req/min. We sleep 1.1s between calls to stay well under.
"""
from pathlib import Path
import pandas as pd
import time
from v17.data.calendar.finnhub_client import backfill_calendar


def monthly_ranges(start: str, end: str):
    cur = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    while cur < end_ts:
        nxt = cur + pd.offsets.MonthBegin(1)
        yield cur.strftime("%Y-%m-%d"), min(nxt, end_ts).strftime("%Y-%m-%d")
        cur = nxt


def main() -> None:
    frames = []
    for s, e in monthly_ranges("2015-01-01", "2026-10-18"):
        print(f"fetching {s} .. {e}", flush=True)
        try:
            df = backfill_calendar(s, e, currencies=["USD", "EUR", "GBP"], impact="high")
            frames.append(df)
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN: {exc}; skipping chunk", flush=True)
        time.sleep(1.1)
    all_df = (
        pd.concat(frames, ignore_index=True)
        .sort_values("timestamp_utc")
        .drop_duplicates()
    )
    out = Path("data/calendar/economic_events.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    all_df.to_parquet(out, index=False)
    print(f"wrote {len(all_df)} events to {out}", flush=True)


if __name__ == "__main__":
    main()
