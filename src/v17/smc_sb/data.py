"""Data loading, holdout guard, integrity checks and candle building (spec §12, D15, R1-R3, R20, R23).

`Market` holds validated M1 bid/ask arrays (UTC epoch-ns bar starts) plus mid OHLC, 5/15-minute candles
aligned to the NY wall clock, and the NY-17:00 daily table. Nothing here fills or substitutes missing data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from v17.smc_sb.config import INSTRUMENTS
from v17.smc_sb.session import NS_PER_MIN, ny_wall, trading_date_of

REPO = Path(__file__).resolve().parents[3]
DEV_CONTEXT_START = pd.Timestamp("2017-11-01", tz="America/New_York")  # warm-up context only
DEV_END = pd.Timestamp("2025-01-01", tz="America/New_York")  # exclusive
FIELDS = ("o", "h", "l", "c")


class DataIntegrityError(RuntimeError):
    """Raised instead of silently repairing bad data."""


class HoldoutAccessError(RuntimeError):
    """Raised on any attempt to read final-exam data before review sign-off."""


def _source_path(symbol: str) -> tuple[Path, bool]:
    paired = REPO / "data" / "bars_m1_paired" / symbol
    if paired.exists():
        return paired, True
    return REPO / ".worktrees" / "sb-6-engine-gate" / "data" / "bars" / symbol / "dev", False


def source_files(instrument: str) -> list[Path]:
    path, _ = _source_path(INSTRUMENTS[instrument])
    return sorted(path.rglob("*.parquet"))


def load_m1(instrument: str, *, final_exam: bool = False) -> pd.DataFrame:
    """Development M1 bid/ask for `instrument`, restricted to [2017-11-01, 2025-01-01) NY.

    The final exam (2012-2014) is locked until the implementation and data audit are reviewed (D15).
    """
    if final_exam:
        raise HoldoutAccessError("final-exam data (2012-2014) is locked until review sign-off")
    files = source_files(instrument)
    if not files:
        raise FileNotFoundError(f"no M1 parquet files for {instrument}")
    cols = ["ts_utc", *[f"{s}_{f}" for s in ("bid", "ask") for f in FIELDS]]
    table = pa.concat_tables([pq.read_table(f, columns=cols) for f in files])
    df: pd.DataFrame = table.to_pandas()
    lo, hi = DEV_CONTEXT_START.value, DEV_END.value
    out: pd.DataFrame = df[(df.ts_utc >= lo) & (df.ts_utc < hi)].reset_index(drop=True)
    return out


def validate_m1(df: pd.DataFrame) -> pd.DataFrame:
    """Sort and verify; raise DataIntegrityError on duplicates, NaN, non-positive or crossed quotes."""
    df = df.sort_values("ts_utc", kind="mergesort").reset_index(drop=True)
    if df.ts_utc.duplicated().any():
        raise DataIntegrityError(f"{int(df.ts_utc.duplicated().sum())} duplicate M1 timestamps")
    px = df[[f"{s}_{f}" for s in ("bid", "ask") for f in FIELDS]]
    if px.isna().to_numpy().any():
        raise DataIntegrityError("NaN prices in M1 data")
    if (px <= 0).to_numpy().any():
        raise DataIntegrityError("non-positive prices in M1 data")
    for f in FIELDS:
        if (df[f"ask_{f}"] < df[f"bid_{f}"]).any():
            raise DataIntegrityError(f"crossed quotes (ask_{f} < bid_{f})")
    for s in ("bid", "ask"):
        if (
            (df[f"{s}_h"] < df[[f"{s}_o", f"{s}_c", f"{s}_l"]].max(axis=1))
            | (df[f"{s}_l"] > df[[f"{s}_o", f"{s}_c"]].min(axis=1))
        ).any():
            raise DataIntegrityError(f"inconsistent {s} OHLC (high/low do not bound open/close)")
    return df


def widen_costs(df: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    """R23: scale each bar's spread by `multiplier` symmetrically around mid (mid prices unchanged)."""
    if multiplier == 1.0:
        return df
    out = df.copy()
    for f in FIELDS:
        mid = (df[f"bid_{f}"] + df[f"ask_{f}"]) / 2
        half = (df[f"ask_{f}"] - df[f"bid_{f}"]) / 2 * multiplier
        out[f"bid_{f}"], out[f"ask_{f}"] = mid - half, mid + half
    return out


def build_candles(
    ts: np.ndarray,
    o: np.ndarray,
    h: np.ndarray,
    lo: np.ndarray,
    c: np.ndarray,
    minutes: int,
) -> pd.DataFrame:
    """R3: candles from available M1 bars, aligned to the NY wall clock.

    NY's UTC offset is a whole number of hours, so flooring UTC epoch-ns to a 5/15-minute grid equals NY
    alignment. Empty bins produce no candle; `n_m1` records how many M1 bars formed each candle.
    """
    width = minutes * NS_PER_MIN
    key = ts // width
    starts, first = np.unique(key, return_index=True)
    last = np.r_[first[1:], len(ts)] - 1
    return pd.DataFrame(
        {
            "start": starts * width,
            "end": starts * width + width,
            "o": o[first],
            "h": np.maximum.reduceat(h, first),
            "l": np.minimum.reduceat(lo, first),
            "c": c[last],
            "n_m1": last - first + 1,
        }
    )


@dataclass
class Market:
    instrument: str
    ts: np.ndarray
    bid: dict[str, np.ndarray]
    ask: dict[str, np.ndarray]
    mid: dict[str, np.ndarray]
    c5: pd.DataFrame
    c15: pd.DataFrame
    daily: pd.DataFrame  # index = trading date (Timestamp), cols o,h,l,c,first_ns
    asia: pd.DataFrame  # index = trading date, cols h,l

    def day_pos(self, day: pd.Timestamp) -> int:
        """Position of a trading date in the daily table, or -1."""
        return int(self.daily.index.get_indexer(pd.DatetimeIndex([day]))[0])

    def idx(self, t_ns: int) -> int:
        """First M1 bar index with start >= t_ns."""
        return int(np.searchsorted(self.ts, t_ns, side="left"))


def build_market(
    instrument: str,
    m1: pd.DataFrame,
    *,
    rollover_hour: int = 17,
    asia_start_hour: int = 20,
    fvg_tf: int = 5,
    mss_tf: int = 15,
) -> Market:
    df = validate_m1(m1)
    ts = df.ts_utc.to_numpy(np.int64)
    bid = {f: df[f"bid_{f}"].to_numpy(float) for f in FIELDS}
    ask = {f: df[f"ask_{f}"].to_numpy(float) for f in FIELDS}
    mid = {f: (bid[f] + ask[f]) / 2 for f in FIELDS}
    # mid high/low: (bid_h + ask_h)/2 is the mid-quote high proxy used by all prior cycles (R2).
    c5 = build_candles(ts, mid["o"], mid["h"], mid["l"], mid["c"], fvg_tf)
    c15 = build_candles(ts, mid["o"], mid["h"], mid["l"], mid["c"], mss_tf)
    td = trading_date_of(ts, rollover_hour)
    frame = pd.DataFrame(
        {"td": td, "o": mid["o"], "h": mid["h"], "l": mid["l"], "c": mid["c"], "ts": ts}
    )
    daily = frame.groupby("td", sort=True).agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), first_ns=("ts", "first")
    )
    daily.index = pd.DatetimeIndex(daily.index)
    daily = daily[daily.index.dayofweek < 5]
    hour = ny_wall(ts).hour.to_numpy()
    a = frame[hour >= asia_start_hour]
    asia = a.groupby("td", sort=True).agg(h=("h", "max"), l=("l", "min"))
    asia.index = pd.DatetimeIndex(asia.index)
    return Market(instrument, ts, bid, ask, mid, c5, c15, daily, asia)
