from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

_NY = ZoneInfo("America/New_York")
_LDN = ZoneInfo("Europe/London")

SB_START = time(3, 0)
SB_END = time(4, 0)
# ICT Silver Bullet: three NY-time windows per day.
# London SB (03-04), NY AM SB (10-11, post-equity-open), NY PM SB (14-15).
SB_WINDOWS: tuple[tuple[time, time], ...] = (
    (time(3, 0), time(4, 0)),
    (time(10, 0), time(11, 0)),
    (time(14, 0), time(15, 0)),
)
JUDAS_START = time(7, 0)
JUDAS_END = time(10, 0)


def _local_time(ts: datetime, tz: ZoneInfo) -> time:
    return ts.astimezone(tz).time()


def _local_between(ts: datetime, tz: ZoneInfo, start: time, end: time) -> bool:
    t = _local_time(ts, tz)
    return start <= t < end


def in_silver_bullet_window(ts: datetime) -> bool:
    t = _local_time(ts, _NY)
    return any(start <= t < end for start, end in SB_WINDOWS)


def in_judas_window(ts: datetime) -> bool:
    return _local_between(ts, _LDN, JUDAS_START, JUDAS_END)


def window_id_for(ts: datetime) -> str | None:
    """Return a stable window identifier for dedupe keys.

    Allows at most one trade per (setup, side) per window per day:
    SB London (03-04 NY), SB NY-AM (10-11 NY), SB NY-PM (14-15 NY), Judas.
    """
    t_ny = _local_time(ts, _NY)
    for i, (start, end) in enumerate(SB_WINDOWS):
        if start <= t_ny < end:
            return f"sb_{i}"
    if _local_between(ts, _LDN, JUDAS_START, JUDAS_END):
        return "judas"
    return None


def window_id_for_setup(setup_name: str, ts: datetime) -> str | None:
    """Return a setup-aware window identifier for dedupe keys.

    Judas Swing fires at most once per London session per day.
    Silver Bullet fires at most once per SB window (London, NY AM, NY PM) per day.
    """
    date_str = ts.strftime("%Y%m%d")
    if setup_name == "silver_bullet":
        t_ny = _local_time(ts, _NY)
        for i, (start, end) in enumerate(SB_WINDOWS):
            if start <= t_ny < end:
                return f"sb_{i}_{date_str}"
        return None
    elif setup_name == "judas_swing":
        if _local_between(ts, _LDN, JUDAS_START, JUDAS_END):
            return f"judas_{date_str}"
        return None
    return f"{setup_name}_{date_str}"


def asian_range(ts_today: datetime) -> tuple[datetime, datetime]:
    ny_today = ts_today.astimezone(_NY)
    ny_prev = ny_today - timedelta(days=1)
    start_ny = ny_prev.replace(hour=19, minute=0, second=0, microsecond=0)
    end_ny = ny_today.replace(hour=2, minute=0, second=0, microsecond=0)
    return start_ny.astimezone(ts_today.tzinfo), end_ny.astimezone(ts_today.tzinfo)


def asian_high_low(bars_1m: pd.DataFrame, ts_today: datetime) -> tuple[float, float]:
    start, end = asian_range(ts_today)
    m = (bars_1m["ts"] >= pd.Timestamp(start)) & (bars_1m["ts"] < pd.Timestamp(end))
    sub = bars_1m[m]
    if sub.empty:
        raise ValueError("no bars inside asian range")
    return float(sub["high"].max()), float(sub["low"].min())
