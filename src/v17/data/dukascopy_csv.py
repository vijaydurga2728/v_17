from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd

from v17.common.errors import V17DataError

EXPECTED_OHLCV: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")
_EXPECTED_COLS = 1 + len(EXPECTED_OHLCV)  # time column + OHLCV

# Dukascopy export conventions. Column 0 varies by user's export choice.
TIME_SOURCES: dict[str, tuple[str, str | None]] = {
    # column 0 header -> (strptime fmt, source tz; None=UTC)
    "Gmt time": ("%d.%m.%Y %H:%M:%S.%f", None),
    "Local time": ("%d.%m.%Y %H:%M:%S.%f%z", None),  # tz is in the string
    "Time (EET)": ("%Y.%m.%d %H:%M:%S", "Europe/Helsinki"),  # EET + DST = Helsinki
}


def parse_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as fh:
        first = fh.readline().rstrip("\r\n")
    return [c.strip().strip('"') for c in first.split(",")]


def _detect_time_format(cols: list[str]) -> tuple[str, str, str | None]:
    """Returns (time_col_name, strptime_fmt, source_tz_or_None)."""
    if len(cols) < _EXPECTED_COLS:
        raise V17DataError("CSV must have 6 columns", got=cols)
    tcol = cols[0]
    if tcol not in TIME_SOURCES:
        raise V17DataError(
            "unknown time column", got=tcol, expected=list(TIME_SOURCES.keys())
        )
    rest = tuple(cols[1:6])
    if rest != EXPECTED_OHLCV:
        raise V17DataError("unexpected OHLCV columns", got=rest, want=list(EXPECTED_OHLCV))
    fmt, tz = TIME_SOURCES[tcol]
    return tcol, fmt, tz


def validate_schema(path: Path) -> None:
    cols = parse_header(path)
    _detect_time_format(cols)


def read_file(path: Path, side: Literal["bid", "ask"]) -> pd.DataFrame:
    cols = parse_header(path)
    tcol, fmt, tz = _detect_time_format(cols)
    df = pd.read_csv(
        path,
        dtype={"Open": "float64", "High": "float64", "Low": "float64", "Close": "float64"},
    )
    # Rename trailing-space-tolerant: pandas keeps header verbatim; use positional
    df.columns = [c.strip() for c in df.columns]
    if tz is None:
        df["ts"] = pd.to_datetime(df[tcol], format=fmt, utc=True)
    else:
        naive = pd.to_datetime(df[tcol], format=fmt)
        localized = naive.dt.tz_localize(
            tz, ambiguous="NaT", nonexistent="shift_forward"
        )
        df["ts"] = localized.dt.tz_convert("UTC")
    df = df.rename(
        columns={
            "Open": f"open_{side}",
            "High": f"high_{side}",
            "Low": f"low_{side}",
            "Close": f"close_{side}",
            "Volume": "volume",
        }
    )
    # Volume can be float in real Dukascopy exports; keep as float64 pre-stitch.
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("float64")
    out = df[
        [
            "ts",
            f"open_{side}",
            f"high_{side}",
            f"low_{side}",
            f"close_{side}",
            "volume",
        ]
    ].copy()
    out = out.dropna(subset=["ts"])
    out = out.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    return out


def _pip_scale(sample_price: float, symbol: str | None = None) -> int:
    """Pip scale per symbol family.

    FX major pairs: 10000 (1 pip = 0.0001).
    JPY pairs: 100 (1 pip = 0.01).
    Indices and commodities: 1 (1 point = 1.0).
    Symbol-aware when provided; sample_price fallback for legacy callers.
    """
    if symbol is not None:
        if symbol.endswith("JPY"):
            return 100
        if symbol in {"USATECHIDXUSD", "USA500IDXUSD", "USA30IDXUSD"}:
            return 1
        if symbol in {"XAUUSD", "XAGUSD", "BTCUSD"}:
            return 1
        return 10000
    # Heuristic fallback by price magnitude.
    if sample_price >= 1000.0:
        return 1  # index/crypto scale
    if sample_price >= 50.0:
        return 100  # JPY-ish
    return 10000  # FX majors


def stitch_pair(
    bid_paths: list[Path], ask_paths: list[Path], symbol: str | None = None
) -> pd.DataFrame:
    bids = pd.concat([read_file(p, "bid") for p in bid_paths], ignore_index=True)
    asks = pd.concat([read_file(p, "ask") for p in ask_paths], ignore_index=True)
    bids = bids.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    asks = asks.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    df = pd.merge(bids, asks, on="ts", how="inner", validate="one_to_one")
    scale = _pip_scale(float(df["close_bid"].iloc[0]), symbol)
    out = pd.DataFrame(
        {
            "ts": df["ts"],
            "open": (df["open_bid"] + df["open_ask"]) / 2.0,
            "high": (df["high_bid"] + df["high_ask"]) / 2.0,
            "low": (df["low_bid"] + df["low_ask"]) / 2.0,
            "close": (df["close_bid"] + df["close_ask"]) / 2.0,
            "volume": df["volume_x"].fillna(0).astype("int64"),
            "spread_pips": (df["close_ask"] - df["close_bid"]) * scale,
        }
    )
    if not out["ts"].is_monotonic_increasing:
        raise V17DataError("stitched timestamps not monotonic")
    return out
