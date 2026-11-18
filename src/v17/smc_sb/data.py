"""Data loading, holdout guard, integrity checks and candle building (spec §12, D15, R1-R3, R20, R23,
R27-R30).

`Market` holds validated M1 bid/ask arrays (UTC epoch-ns bar starts) plus mid OHLC, 5/15-minute candles
aligned to the NY wall clock, and the NY-17:00 daily table restricted to valid XNYS sessions.
Nothing here fills or substitutes missing data.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from v17.smc_sb.config import INSTRUMENTS
from v17.smc_sb.session import NS_PER_MIN, ny_ns, ny_wall, trading_date_of, xnys_schedule

REPO = Path(__file__).resolve().parents[3]
DEV_CONTEXT_START = pd.Timestamp("2017-11-01", tz="America/New_York")  # warm-up context only
DEV_END = pd.Timestamp("2025-01-01", tz="America/New_York")  # exclusive
FIELDS = ("o", "h", "l", "c")
PX_COLS = [f"{s}_{f}" for s in ("bid", "ask") for f in FIELDS]


class DataIntegrityError(RuntimeError):
    """Raised instead of silently repairing bad data."""


class HoldoutAccessError(RuntimeError):
    """Raised on any attempt to read final-exam data before review sign-off."""


def _source_path(symbol: str) -> Path:
    paired = REPO / "data" / "bars_m1_paired" / symbol
    if paired.exists():
        return paired
    return REPO / ".worktrees" / "sb-6-engine-gate" / "data" / "bars" / symbol / "dev"


def source_files(instrument: str) -> list[Path]:
    return sorted(_source_path(INSTRUMENTS[instrument]).rglob("*.parquet"))


def load_m1(instrument: str, *, final_exam: bool = False) -> pd.DataFrame:
    """Development M1 bid/ask for `instrument`, restricted to [2017-11-01, 2025-01-01) NY.

    The final exam (2012-2014) is locked until the implementation and data audit are reviewed (D15).
    """
    if final_exam:
        raise HoldoutAccessError("final-exam data (2012-2014) is locked until review sign-off")
    files = source_files(instrument)
    if not files:
        raise FileNotFoundError(f"no M1 parquet files for {instrument}")
    table = pa.concat_tables([pq.read_table(f, columns=["ts_utc", *PX_COLS]) for f in files])
    df: pd.DataFrame = table.to_pandas()
    lo, hi = DEV_CONTEXT_START.value, DEV_END.value
    out: pd.DataFrame = df[(df.ts_utc >= lo) & (df.ts_utc < hi)].reset_index(drop=True)
    return out


def validate_m1(df: pd.DataFrame) -> pd.DataFrame:
    """Sort and verify; raise DataIntegrityError on duplicates, NaN, non-positive or inconsistent OHLC.

    Crossed quotes are NOT repaired here: `crossed_mask` reports them and `build_market` excludes their
    whole sessions (R27).
    """
    df = df.sort_values("ts_utc", kind="mergesort").reset_index(drop=True)
    if df.ts_utc.duplicated().any():
        raise DataIntegrityError(f"{int(df.ts_utc.duplicated().sum())} duplicate M1 timestamps")
    px = df[PX_COLS]
    if px.isna().to_numpy().any():
        raise DataIntegrityError("NaN prices in M1 data")
    if (px <= 0).to_numpy().any():
        raise DataIntegrityError("non-positive prices in M1 data")
    for s in ("bid", "ask"):
        bad = (df[f"{s}_h"] < df[[f"{s}_o", f"{s}_c", f"{s}_l"]].max(axis=1)) | (
            df[f"{s}_l"] > df[[f"{s}_o", f"{s}_c"]].min(axis=1)
        )
        if bad.any():
            raise DataIntegrityError(f"inconsistent {s} OHLC (high/low do not bound open/close)")
    return df


def crossed_mask(df: pd.DataFrame) -> np.ndarray:
    """R27: True where ask < bid on any of open/high/low/close."""
    m = np.zeros(len(df), dtype=bool)
    for f in FIELDS:
        m |= (df[f"ask_{f}"] < df[f"bid_{f}"]).to_numpy()
    return m


def frozen_side_mask(df: pd.DataFrame, min_run: int) -> np.ndarray:
    """R31 (proposed): True on bars inside a run of >= `min_run` consecutive bars where one quote side is flat
    (o=h=l=c) and unchanged from the previous bar while the other side moves (stale feed, e.g. US30 March 2020)."""
    out = np.zeros(len(df), dtype=bool)
    if len(df) < 2:
        return out
    for side, other in (("ask", "bid"), ("bid", "ask")):
        a = df[[f"{side}_{f}" for f in FIELDS]].to_numpy()
        b = df[[f"{other}_{f}" for f in FIELDS]].to_numpy()
        flag = np.r_[
            False,
            np.all(a[1:] == a[:-1], axis=1)
            & np.all(a[1:, :1] == a[1:, 1:], axis=1)
            & np.any(b[1:] != b[:-1], axis=1),
        ]
        d = np.diff(np.r_[0, flag.astype(np.int8), 0])
        starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
        for st, en in zip(starts, ends, strict=True):
            if en - st >= min_run:
                out[st:en] = True
    return out


def repeat_mask(df: pd.DataFrame) -> np.ndarray:
    """R30: True where all 8 bid/ask OHLC values equal the previous bar's (provider-filled minute)."""
    px = df[PX_COLS].to_numpy()
    out = np.zeros(len(df), dtype=bool)
    if len(df) > 1:
        out[1:] = np.all(px[1:] == px[:-1], axis=1)
    return out


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
    repeat: np.ndarray  # R30 flag per M1 bar
    c5: pd.DataFrame
    c15: pd.DataFrame
    daily: pd.DataFrame  # valid XNYS sessions only; index = trading date; cols o,h,l,c
    asia: pd.DataFrame  # index = trading date, cols h,l
    xnys: frozenset[dt.date]
    early_close: frozenset[dt.date]
    excluded_sessions: tuple[dt.date, ...] = ()
    excluded_ranges: np.ndarray = field(default_factory=lambda: np.empty((0, 2), dtype=np.int64))
    non_xnys_sessions: tuple[dt.date, ...] = ()
    exclusion_reason: dict[dt.date, str] = field(default_factory=dict)

    def idx(self, t_ns: int) -> int:
        """First M1 bar index with start >= t_ns."""
        return int(np.searchsorted(self.ts, t_ns, side="left"))

    def day_pos(self, day: pd.Timestamp) -> int:
        """Position of a trading date in the daily table, or -1."""
        return int(self.daily.index.get_indexer(pd.DatetimeIndex([day]))[0])

    def contaminated(self, a_ns: int, b_ns: int) -> bool:
        """R5a: does [a_ns, b_ns) intersect any excluded (crossed-quote) session?"""
        r = self.excluded_ranges
        return bool(len(r) and np.any((r[:, 0] < b_ns) & (r[:, 1] > a_ns)))


def build_market(
    instrument: str,
    m1: pd.DataFrame,
    *,
    xnys: Sequence[dt.date] | None = None,
    early_close: Sequence[dt.date] | None = None,
    rollover_hour: int = 17,
    asia_start_hour: int = 20,
    stale_min_run: int | None = 30,
    fvg_tf: int = 5,
    mss_tf: int = 15,
) -> Market:
    df = validate_m1(m1)
    td_all = trading_date_of(df.ts_utc.to_numpy(np.int64), rollover_hour)
    # R27: drop every session that contains a crossed quote (mapped by code, no hardcoded dates);
    # R31 (proposed): also every session containing a frozen-quote-side run of >= stale_min_run bars.
    crossed = crossed_mask(df)
    stale = frozen_side_mask(df, stale_min_run) if stale_min_run else np.zeros(len(df), dtype=bool)
    bad = np.unique(td_all[crossed | stale])
    excluded = tuple(pd.Timestamp(d).date() for d in bad)
    reasons = {
        pd.Timestamp(d).date(): ("crossed_quotes" if np.any(crossed[td_all == d]) else "")
        + ("+" if np.any(crossed[td_all == d]) and np.any(stale[td_all == d]) else "")
        + ("frozen_quote_side" if np.any(stale[td_all == d]) else "")
        for d in bad
    }
    keep = ~np.isin(td_all, bad)
    df, td = df[keep].reset_index(drop=True), td_all[keep]
    if df.empty:
        raise DataIntegrityError("no M1 bars left after excluding bad-quote sessions")
    hh = f"{rollover_hour:02d}:00"
    ranges = np.array(
        [[ny_ns(d - dt.timedelta(days=1), hh), ny_ns(d, hh)] for d in excluded], dtype=np.int64
    ).reshape(-1, 2)
    if xnys is None or early_close is None:
        first = pd.Timestamp(td_all[0]).date() if len(td_all) else dt.date(2000, 1, 1)
        last = pd.Timestamp(td_all[-1]).date() if len(td_all) else dt.date(2000, 1, 1)
        sessions, early = xnys_schedule(first.isoformat(), last.isoformat())
        xnys = sessions if xnys is None else xnys
        early_close = sorted(early) if early_close is None else early_close
    xset = frozenset(xnys)

    ts = df.ts_utc.to_numpy(np.int64)
    bid = {f: df[f"bid_{f}"].to_numpy(float) for f in FIELDS}
    ask = {f: df[f"ask_{f}"].to_numpy(float) for f in FIELDS}
    mid = {f: (bid[f] + ask[f]) / 2 for f in FIELDS}
    c5 = build_candles(ts, mid["o"], mid["h"], mid["l"], mid["c"], fvg_tf)
    c15 = build_candles(ts, mid["o"], mid["h"], mid["l"], mid["c"], mss_tf)
    frame = pd.DataFrame({"td": td, "o": mid["o"], "h": mid["h"], "l": mid["l"], "c": mid["c"]})
    daily = frame.groupby("td", sort=True).agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last")
    )
    daily.index = pd.DatetimeIndex(daily.index)
    in_x = np.array([d.date() in xset for d in daily.index], dtype=bool)
    non_x = tuple(d.date() for d in daily.index[~in_x])
    daily = daily[in_x]  # R29: XNYS sessions only (R27 sessions already removed)
    hour = ny_wall(ts).hour.to_numpy()
    asia = (
        frame[hour >= asia_start_hour].groupby("td", sort=True).agg(h=("h", "max"), l=("l", "min"))
    )
    asia.index = pd.DatetimeIndex(asia.index)
    return Market(
        instrument,
        ts,
        bid,
        ask,
        mid,
        repeat_mask(df),
        c5,
        c15,
        daily,
        asia,
        xset,
        frozenset(early_close),
        excluded,
        ranges,
        non_x,
        reasons,
    )
