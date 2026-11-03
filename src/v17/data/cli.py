from __future__ import annotations

from pathlib import Path

import httpx
import typer

from v17.common.clock import SystemClock
from v17.common.types import Symbol
from v17.config import get_settings
from v17.data.calendar.ff_json import fetch_current_week
from v17.data.dukascopy_csv import stitch_pair
from v17.data.parquet_store import write_1m


def _bid_ask_paths(csv_dir: Path, symbol: str) -> tuple[list[Path], list[Path]]:
    bids = sorted(csv_dir.glob(f"{symbol}_1 Min_Bid_*.csv"))
    asks = sorted(csv_dir.glob(f"{symbol}_1 Min_Ask_*.csv"))
    if not bids or not asks:
        raise typer.BadParameter(f"no bid/ask CSVs for {symbol} under {csv_dir}")
    return bids, asks


def ingest(symbol: str = typer.Option(..., "--symbol")) -> None:
    s = get_settings()
    s.ensure_dirs()
    csv_dir = s.dukascopy_csv_dir or (s.data / "raw")
    bids, asks = _bid_ask_paths(csv_dir, symbol)
    df = stitch_pair(bids, asks, symbol=symbol)
    write_1m(df, Symbol(symbol), s.parquet_root)
    typer.echo(f"wrote {len(df)} rows for {symbol} to {s.parquet_root}")


def ingest_calendar() -> None:
    s = get_settings()
    s.ensure_dirs()
    with httpx.Client() as http:
        events = fetch_current_week(http, s.calendar_root, SystemClock().now())
    typer.echo(f"cached {len(events)} events to {s.calendar_root}")
