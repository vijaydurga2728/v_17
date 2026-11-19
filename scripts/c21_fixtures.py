"""Cycle 21 targeted synthetic fixtures (review round 3, section 3). Deterministic, hand-designed M1 bid/ask days
that force the branches the random seeds never reached. Used by `c21_fixture_parity.py` and the pytest wrapper.

Base day (same as tests/unit/smc_sb/conftest.py): Monday 2024-03-18, bullish HH+HL bias (EQ 103), PDH/PDL 109/99,
sweep of PDL by the 10:00 5m candle, 15m MSS at 10:30 over swing 102.0, FVG [101.2, 101.6] formed 10:30,
long limit 101.6, stop 101.2, 1R = 0.9, target PDH 109.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

NY = "America/New_York"
SPREAD = 0.2
DAY = dt.date(2024, 3, 18)
PRIOR_H = [100, 102, 110, 103, 101, 104, 115, 105, 103, 108, 109]
PRIOR_L = [90, 92, 95, 93, 89, 94, 98, 96, 91, 97, 99]
BASE = [
    ("08:30", 101.0, 101.3, 100.9, 101.1), ("08:35", 101.1, 101.3, 100.9, 101.0), ("08:40", 101.0, 101.2, 100.8, 101.0),
    ("08:45", 101.0, 101.4, 100.9, 101.1), ("08:50", 101.1, 101.3, 100.9, 101.0), ("08:55", 101.0, 101.2, 100.9, 101.0),
    ("09:00", 101.0, 101.5, 100.9, 101.2), ("09:05", 101.2, 101.4, 101.0, 101.1), ("09:10", 101.1, 101.3, 101.0, 101.2),
    ("09:15", 101.2, 101.6, 101.1, 101.4), ("09:20", 101.4, 101.5, 101.2, 101.3), ("09:25", 101.3, 101.5, 101.2, 101.5),
    ("09:30", 101.5, 102.0, 101.4, 101.8), ("09:35", 101.8, 101.9, 101.3, 101.4), ("09:40", 101.4, 101.5, 100.9, 101.0),
    ("09:45", 101.0, 101.1, 100.2, 100.4), ("09:50", 100.4, 100.5, 99.8, 99.9), ("09:55", 99.9, 100.0, 99.4, 99.5),
    ("10:00", 99.5, 99.6, 98.5, 99.4), ("10:05", 99.4, 100.3, 99.3, 100.2), ("10:10", 100.2, 101.0, 100.1, 100.9),
    ("10:15", 100.9, 101.2, 100.8, 101.1), ("10:20", 101.1, 102.4, 101.0, 102.3), ("10:25", 102.3, 102.6, 101.6, 102.5),
    ("10:30", 102.5, 102.6, 101.35, 101.7), ("10:35", 101.7, 103.0, 101.7, 103.0), ("10:40", 103.0, 105.0, 103.0, 105.0),
    ("10:45", 105.0, 109.5, 105.0, 109.2),
]  # fmt: skip


def m1_frame(
    rows: list[tuple[str, float, float, float, float]], spread: float = SPREAD
) -> pd.DataFrame:
    ts = pd.DatetimeIndex([r[0] for r in rows]).tz_localize(NY).tz_convert("UTC").as_unit("ns").asi8
    df = pd.DataFrame({"ts_utc": ts})
    for k, f in enumerate("ohlc", start=1):
        mid = pd.Series([r[k] for r in rows], dtype=float)
        df[f"bid_{f}"], df[f"ask_{f}"] = mid - spread / 2, mid + spread / 2
    return df


def five_min(day: str, hhmm: str, o: float, h: float, l: float, c: float) -> list[tuple]:  # noqa: E741
    seq = [o, l, h, c, c] if c >= o else [o, h, l, c, c]
    t0 = pd.Timestamp(f"{day} {hhmm}")
    return [
        ((t0 + pd.Timedelta(minutes=k)).strftime("%Y-%m-%d %H:%M"), p, p, p, p)
        for k, p in enumerate(seq)
    ]


def day_rows(
    candles: list[tuple],
    tail: float | list[tuple] = 109.2,
    extra: list[tuple] | None = None,
    drop: set[str] | None = None,
) -> list[tuple]:
    """Prior 11 daily bars (12:00) + the 5m candles + flat tail from 10:50 to 15:59 (or explicit tail rows)."""
    rows: list[tuple] = list(extra or [])
    prior = pd.bdate_range(end=pd.Timestamp(DAY) - pd.Timedelta(days=1), periods=len(PRIOR_H))
    for k, d in enumerate(prior):
        h, l = PRIOR_H[k], PRIOR_L[k]  # noqa: E741
        mid = 101.0 if k == len(PRIOR_H) - 1 else (h + l) / 2
        rows.append((f"{d.date()} 12:00", mid, h, l, mid))
    ds = DAY.isoformat()
    for c in candles:
        rows += five_min(ds, *c)
    if isinstance(tail, list):
        rows += tail
    else:
        last = max(pd.Timestamp(f"{ds} {c[0]}") for c in candles) + pd.Timedelta(minutes=5)
        t = last
        while t < pd.Timestamp(f"{ds} 16:00"):
            rows.append((t.strftime("%Y-%m-%d %H:%M"), tail, tail, tail, tail))
            t += pd.Timedelta(minutes=1)
    rows.sort(key=lambda r: r[0])
    return [r for r in rows if not drop or r[0][11:] not in drop or not r[0].startswith(ds)]


def mirror(df: pd.DataFrame, k: float = 200.0) -> pd.DataFrame:
    """Price reflection p -> k - p (bid/ask and high/low swap): a long day becomes the equivalent short day."""
    out = pd.DataFrame({"ts_utc": df.ts_utc})
    for a, b in (("o", "o"), ("h", "l"), ("l", "h"), ("c", "c")):
        out[f"bid_{a}"] = k - df[f"ask_{b}"]
        out[f"ask_{a}"] = k - df[f"bid_{b}"]
    return out[["ts_utc", *[f"{s}_{f}" for s in ("bid", "ask") for f in "ohlc"]]]


def replace(candles: list[tuple], **new: tuple) -> list[tuple]:
    out = list(candles)
    for hhmm, vals in new.items():
        key = hhmm.replace("h", ":")
        i = next(i for i, c in enumerate(out) if c[0] == key)
        out[i] = (key, *vals)
    return out


@dataclass
class Fixture:
    name: str
    requirement: str
    m1: pd.DataFrame
    model: str = "A"
    expiry: str = "11:05"
    early: list[dt.date] = field(default_factory=list)
    expect_reason: str = "trade"
    expect: dict[str, object] = field(
        default_factory=dict
    )  # trade field -> value (floats compared at 1e-9)


def _flat(t: str, p: float) -> tuple:
    return (f"{DAY} {t}", p, p, p, p)


def fixtures() -> list[Fixture]:
    fx: list[Fixture] = []
    # 1. gap-through long stop: after the 10:32 fill, the 10:35 bar opens at 100.0 (bid 99.9 < stop 101.2)
    c = replace(BASE, **{"10h35": (100.0, 100.2, 99.8, 100.1)})
    c = [x for x in c if x[0] not in ("10:40", "10:45")]
    fx.append(
        Fixture(
            "gap_long_stop",
            "Gap-through long stop: fill at opening bid minus 0.5",
            m1_frame(day_rows(c, tail=100.1)),
            expect={
                "exit_reason": "stop",
                "gap_through": True,
                "exit_price": 99.9 - 0.5,
                "exit_hhmm": "10:35",
            },
        )
    )
    # 2. gap-through short stop: mirror of 1 (short limit 98.4, stop 98.8; 10:35 ask open 100.1 > stop)
    fx.append(
        Fixture(
            "gap_short_stop",
            "Gap-through short stop: fill at opening ask plus 0.5",
            mirror(m1_frame(day_rows(c, tail=100.1))),
            expect={
                "side": -1,
                "exit_reason": "stop",
                "gap_through": True,
                "exit_price": 200 - 99.9 + 0.5,
                "exit_hhmm": "10:35",
            },
        )
    )
    # 3. no target, no stop -> force close on the 15:59 bar
    c3 = [x for x in BASE if x[0] not in ("10:40", "10:45")]
    fx.append(
        Fixture(
            "force_close_1559",
            "Force close at the real 15:59 bar (control for case 4)",
            m1_frame(day_rows(c3, tail=103.0)),
            expect={
                "exit_reason": "force_close_16",
                "data_gap": False,
                "exit_hhmm": "15:59",
                "exit_price": 103.0 - 0.1 - 0.5,
            },
        )
    )
    # 4. same day with the 15:59 bar missing -> exit on the last REAL bar (15:58), flagged data_gap; no 16:00 price
    fx.append(
        Fixture(
            "missing_1559",
            "Missing 15:59 bar: no invented 16:00 price; flagged data_gap",
            m1_frame(day_rows(c3, tail=103.0, drop={"15:59"})),
            expect={
                "exit_reason": "force_close_16",
                "data_gap": True,
                "exit_hhmm": "15:58",
                "exit_price": 103.0 - 0.1 - 0.5,
            },
        )
    )
    # 5. early-close date: identical valid setup, but no entry is allowed
    fx.append(
        Fixture(
            "early_close_no_entry",
            "XNYS early-close date: no new entries",
            m1_frame(day_rows(BASE)),
            early=[DAY],
            expect_reason="early_close_day",
        )
    )
    # 6. Model B valid: raise the 10:25 high to 108 -> H = 108, L = 98.5, zone [100.495, 102.11] contains 101.6
    c6 = replace(BASE, **{"10h25": (102.3, 108.0, 101.6, 102.5)})
    fx.append(
        Fixture(
            "ote_valid",
            "Model B: proximal edge inside the 62-79% zone -> order",
            m1_frame(day_rows(c6)),
            model="B",
            expect={"limit": 101.6, "exit_reason": "target"},
        )
    )
    # 7. Model B invalid (base day): zone [99.361, 100.058] does not contain 101.6
    fx.append(
        Fixture(
            "ote_invalid",
            "Model B: proximal edge outside the zone -> rejected",
            m1_frame(day_rows(BASE)),
            model="B",
            expect_reason="ote_proximal_outside_zone",
        )
    )
    # 8. OTE + FVG interaction: H = 106.1316 -> zone [100.10, 101.40] contains the FAR edge 101.2 and part of the
    #    FVG, but not the proximal edge 101.6 -> rejected (overlap alone is not enough)
    c8 = replace(BASE, **{"10h25": (102.3, 106.1316, 101.6, 102.5)})
    fx.append(
        Fixture(
            "ote_overlap_not_proximal",
            "OTE + FVG: FVG overlaps the zone but proximal edge outside",
            m1_frame(day_rows(c8)),
            model="B",
            expect_reason="ote_proximal_outside_zone",
        )
    )
    # 9/10. exact OTE upper boundary (inclusive) and just outside it, found by search (see _boundary_high)
    hb = _boundary_high()
    for name, h, reason in (
        ("ote_upper_boundary_inclusive", hb, "trade"),
        ("ote_upper_boundary_outside", hb - 1e-9, "ote_proximal_outside_zone"),
    ):
        cb = replace(BASE, **{"10h25": (102.3, h, 101.6, 102.5)})
        fx.append(
            Fixture(
                name,
                "OTE zone boundary is inclusive" if reason == "trade" else "Just outside boundary",
                m1_frame(day_rows(cb)),
                model="B",
                expect_reason=reason,
            )
        )
    # 11. multiple setups: first setup sweeps the Asian low 99.5 at 10:00 (PDL 99 untouched), order 10:30 limit 101.6
    #     never fills before a 10:40 test expiry -> cancelled; the re-scan from 10:40 finds a DISTINCT second setup
    #     (PDL 99 swept at 10:40, MSS 11:00, FVG formed 11:00) that forms after the expiry, so it can never be live.
    asia = [
        (f"2024-03-17 {h}:{m:02d}", 101.0, 101.0, 101.0, 101.0)
        for h in (20, 21)
        for m in range(0, 60, 30)
    ]
    asia[1] = ("2024-03-17 20:30", 100.5, 100.5, 99.5, 100.5)
    c11 = replace(
        BASE,
        **{
            "09h55": (99.9, 100.0, 99.6, 99.7),
            "10h00": (99.7, 99.8, 99.2, 99.7),
            "10h30": (102.5, 102.6, 102.0, 102.4),
            "10h35": (102.4, 102.5, 101.9, 102.0),
            "10h40": (102.0, 102.0, 98.8, 99.4),
            "10h45": (99.4, 100.0, 99.3, 99.9),
        },
    )
    c11 += [("10:50", 99.9, 102.6, 99.8, 102.5), ("10:55", 102.5, 103.2, 100.5, 103.0)]
    fx.append(
        Fixture(
            "one_pending_then_rescan",
            "One pending order; cancellation permits a later distinct setup",
            m1_frame(day_rows(c11, tail=103.0, extra=asia)),
            expiry="10:40",
            expect_reason="unfilled_expired",
            expect={"rescan_reason": "setup_after_expiry"},
        )
    )
    # 12. fill bar touches the target -> target ignored on the fill bar; later target hit at 10:47
    c12 = replace(BASE, **{"10h30": (102.5, 102.6, 101.35, 101.7)})
    rows12 = day_rows(c12)
    rows12 = [r if r[0] != f"{DAY} 10:32" else (r[0], 102.5, 109.5, 101.35, 102.0) for r in rows12]
    fx.append(
        Fixture(
            "fill_bar_target_ignored",
            "Target evaluation begins on the bar after the fill",
            m1_frame(rows12),
            expect={"exit_reason": "target", "fill_hhmm": "10:32", "exit_hhmm": "10:47"},
        )
    )
    # 13. fill bar also breaches the stop (opens above it) -> stop on the fill bar at stop - 0.5 (no gap)
    rows13 = [
        r if r[0] != f"{DAY} 10:32" else (r[0], 102.5, 102.5, 101.0, 101.5) for r in day_rows(c12)
    ]
    fx.append(
        Fixture(
            "fill_bar_stop",
            "Stop can trigger on the fill bar",
            m1_frame(rows13),
            expect={
                "exit_reason": "stop",
                "gap_through": False,
                "fill_hhmm": "10:32",
                "exit_hhmm": "10:32",
                "exit_price": 101.2 - 0.5,
            },
        )
    )
    return fx


def _boundary_high() -> float:
    """Smallest 10:25 mid high H (on a fine grid) for which the engine's computed upper OTE edge equals the
    proximal 101.6 exactly in floating point (mids are rebuilt from bid/ask exactly as the engines do)."""

    def mid(p: float) -> float:
        return ((p - SPREAD / 2) + (p + SPREAD / 2)) / 2

    lo, prox = mid(98.5), mid(101.6)
    base = 101.6 + 0.62 * (101.6 - 98.5) / 0.38
    for k in range(-200000, 200000):
        h = base + k * 1e-13
        hm = mid(h)
        if hm - 0.62 * (hm - lo) == prox and hm - 0.79 * (hm - lo) <= prox:
            return h
    raise RuntimeError("no exact boundary value found")
