"""NY session clock helpers (spec §2, R1, R21). DST is handled by zoneinfo, never by fixed offsets."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NY = ZoneInfo("America/New_York")
NS_PER_MIN = 60_000_000_000


def ny_ns(day: dt.date, hhmm: str) -> int:
    """UTC epoch-ns of wall-clock `hhmm` in New York on `day`."""
    h, m = (int(x) for x in hhmm.split(":"))
    return pd.Timestamp(dt.datetime(day.year, day.month, day.day, h, m), tz=NY).value


def ny_wall(ts_ns: np.ndarray) -> pd.DatetimeIndex:
    """Naive NY wall-clock times for UTC epoch-ns timestamps."""
    return (
        pd.DatetimeIndex(pd.to_datetime(ts_ns, unit="ns", utc=True))
        .tz_convert(NY)
        .tz_localize(None)
    )


def trading_date_of(ts_ns: np.ndarray, rollover_hour: int = 17) -> np.ndarray:
    """R1: trading date (datetime64[D]) of each bar; the session closes at `rollover_hour` NY.

    A bar at or after 17:00 NY belongs to the next calendar date's session (Sunday 18:00 -> Monday).
    """
    wall = ny_wall(ts_ns)
    shifted = wall + pd.Timedelta(hours=24 - rollover_hour)
    return shifted.normalize().to_numpy().astype("datetime64[D]")


def xnys_dates(start: str, end: str) -> list[dt.date]:
    """R21: XNYS sessions (incl. early-close days) between start and end inclusive."""
    import pandas_market_calendars as pmc

    sched = pmc.get_calendar("XNYS").schedule(start_date=start, end_date=end)
    return [d.date() for d in sched.index]


def xnys_schedule(start: str, end: str) -> tuple[list[dt.date], set[dt.date]]:
    """R21/R28: (XNYS sessions, early-close sessions whose market close is before 16:00 NY)."""
    import pandas_market_calendars as pmc

    sched = pmc.get_calendar("XNYS").schedule(start_date=start, end_date=end)
    if sched.empty:
        return [], set()
    close_ny = pd.DatetimeIndex(sched["market_close"]).tz_convert(NY)
    early = {
        d.date() for d, c in zip(sched.index, close_ny, strict=True) if (c.hour, c.minute) < (16, 0)
    }
    return [d.date() for d in sched.index], early
