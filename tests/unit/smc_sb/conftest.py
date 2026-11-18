"""Synthetic M1 bid/ask builders for cycle 21 tests (deterministic, no market data)."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pandas as pd
import pytest

from v17.smc_sb.data import build_market

NY = "America/New_York"
SPREAD = 0.2


def m1_frame(
    rows: list[tuple[str, float, float, float, float]], spread: float = SPREAD
) -> pd.DataFrame:
    """rows: (NY wall time 'YYYY-MM-DD HH:MM', mid o, h, l, c) -> M1 bid/ask frame."""
    ts = pd.DatetimeIndex([r[0] for r in rows]).tz_localize(NY).tz_convert("UTC").as_unit("ns").asi8
    df = pd.DataFrame({"ts_utc": ts})
    for k, f in enumerate("ohlc", start=1):
        mid = pd.Series([r[k] for r in rows], dtype=float)
        df[f"bid_{f}"], df[f"ask_{f}"] = mid - spread / 2, mid + spread / 2
    return df


def flat(t: str, p: float) -> tuple[str, float, float, float, float]:
    return (t, p, p, p, p)


def five_min(day: str, hhmm: str, o: float, h: float, l: float, c: float) -> list[tuple]:  # noqa: E741
    """Five flat M1 bars whose 5 m candle is (o, h, l, c). Up candles visit the low first, down candles the high."""
    seq = [o, l, h, c, c] if c >= o else [o, h, l, c, c]
    t0 = pd.Timestamp(f"{day} {hhmm}")
    return [
        flat((t0 + pd.Timedelta(minutes=k)).strftime("%Y-%m-%d %H:%M"), p)
        for k, p in enumerate(seq)
    ]


# ---- the end-to-end scenario (hand-computed in test_engine.py) ----
DAY = dt.date(2024, 3, 18)  # Monday, after the 2024-03-10 DST change
PRIOR_H = [100, 102, 110, 103, 101, 104, 115, 105, 103, 108, 109]
PRIOR_L = [90, 92, 95, 93, 89, 94, 98, 96, 91, 97, 99]
CANDLES_5M = [
    ("08:30", 101.0, 101.3, 100.9, 101.1),
    ("08:35", 101.1, 101.3, 100.9, 101.0),
    ("08:40", 101.0, 101.2, 100.8, 101.0),
    ("08:45", 101.0, 101.4, 100.9, 101.1),
    ("08:50", 101.1, 101.3, 100.9, 101.0),
    ("08:55", 101.0, 101.2, 100.9, 101.0),
    ("09:00", 101.0, 101.5, 100.9, 101.2),
    ("09:05", 101.2, 101.4, 101.0, 101.1),
    ("09:10", 101.1, 101.3, 101.0, 101.2),
    ("09:15", 101.2, 101.6, 101.1, 101.4),
    ("09:20", 101.4, 101.5, 101.2, 101.3),
    ("09:25", 101.3, 101.5, 101.2, 101.5),
    ("09:30", 101.5, 102.0, 101.4, 101.8),
    ("09:35", 101.8, 101.9, 101.3, 101.4),
    ("09:40", 101.4, 101.5, 100.9, 101.0),
    ("09:45", 101.0, 101.1, 100.2, 100.4),
    ("09:50", 100.4, 100.5, 99.8, 99.9),
    ("09:55", 99.9, 100.0, 99.4, 99.5),
    ("10:00", 99.5, 99.6, 98.5, 99.4),  # sweep of PDL 99
    ("10:05", 99.4, 100.3, 99.3, 100.2),
    ("10:10", 100.2, 101.0, 100.1, 100.9),
    ("10:15", 100.9, 101.2, 100.8, 101.1),  # FVG c1 (high 101.2)
    ("10:20", 101.1, 102.4, 101.0, 102.3),  # c2 displacement
    ("10:25", 102.3, 102.6, 101.6, 102.5),  # c3 (low 101.6), MSS close 102.5
    ("10:30", 102.5, 102.6, 101.35, 101.7),  # retrace: fill at 101.6
    ("10:35", 101.7, 103.0, 101.7, 103.0),
    ("10:40", 103.0, 105.0, 103.0, 105.0),
    ("10:45", 105.0, 109.5, 105.0, 109.2),  # target PDH 109
]


def scenario_m1(
    day: dt.date = DAY, candles: list[tuple] | None = None, tail: float = 109.2
) -> pd.DataFrame:
    rows: list[tuple] = []
    prior = pd.bdate_range(end=pd.Timestamp(day) - pd.Timedelta(days=1), periods=len(PRIOR_H))
    for k, d in enumerate(prior):
        h, l = PRIOR_H[k], PRIOR_L[k]  # noqa: E741
        mid = 101.0 if k == len(PRIOR_H) - 1 else (h + l) / 2
        rows.append((f"{d.date()} 12:00", mid, h, l, mid))
    ds = day.isoformat()
    for c in candles or CANDLES_5M:
        rows += five_min(ds, *c)
    t = pd.Timestamp(f"{ds} 10:50")
    while t < pd.Timestamp(f"{ds} 16:00"):
        rows.append(flat(t.strftime("%Y-%m-%d %H:%M"), tail))
        t += pd.Timedelta(minutes=1)
    return m1_frame(rows)


@pytest.fixture
def synth() -> SimpleNamespace:
    return SimpleNamespace(
        m1_frame=m1_frame,
        flat=flat,
        five_min=five_min,
        scenario_m1=scenario_m1,
        DAY=DAY,
        CANDLES_5M=CANDLES_5M,
        build=lambda df, name="NAS100": build_market(name, df),
    )
