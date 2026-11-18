"""PDH/PDL, Asian range (D2), NWOG (D13 / R19) and target selection (D13 / R17 / R18)."""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import pandas as pd

from v17.smc_sb.data import Market
from v17.smc_sb.risk import est_reward, r_unit
from v17.smc_sb.session import ny_ns

NAN = float("nan")


@dataclass(frozen=True)
class DayLevels:
    pdh: float
    pdl: float
    asia_h: float
    asia_l: float
    nwog_lo: float
    nwog_hi: float
    session_start_ns: int  # creation time of PDH/PDL (previous session close)
    nwog_start_ns: int  # creation time of NWOG (Sunday open boundary)


def nwog(mk: Market, day: dt.date, rollover_hour: int = 17) -> tuple[float, float, int]:
    """R19: (lo, hi, start_ns) of the current week's NWOG; NaNs when absent or zero-width.

    lo/hi = min/max of the last mid close before Friday 17:00 NY and the first mid open at/after Sunday 17:00 NY
    (the weekly reopen, normally 18:00).
    """
    sunday = day - dt.timedelta(days=day.weekday() + 1)
    friday = sunday - dt.timedelta(days=2)
    hh = f"{rollover_hour:02d}:00"
    fri_ns, sun_ns = ny_ns(friday, hh), ny_ns(sunday, hh)
    j_close, j_open = mk.idx(fri_ns) - 1, mk.idx(sun_ns)
    if j_close < 0 or j_open >= len(mk.ts):
        return NAN, NAN, sun_ns
    a, b = float(mk.mid["c"][j_close]), float(mk.mid["o"][j_open])
    if a == b:
        return NAN, NAN, sun_ns
    return min(a, b), max(a, b), sun_ns


def day_levels(mk: Market, day: dt.date, i: int, rollover_hour: int = 17) -> DayLevels:
    prev = mk.daily.iloc[i - 1]
    key = pd.Timestamp(day)
    ah, al = _asia(mk, key)
    lo, hi, n_start = nwog(mk, day, rollover_hour)
    start = ny_ns(day - dt.timedelta(days=1), f"{rollover_hour:02d}:00")
    return DayLevels(float(prev.h), float(prev.l), ah, al, lo, hi, start, n_start)


def _asia(mk: Market, key: pd.Timestamp) -> tuple[float, float]:
    k = int(mk.asia.index.get_indexer(pd.DatetimeIndex([key]))[0])
    if k < 0:
        return NAN, NAN
    return float(mk.asia.h.to_numpy()[k]), float(mk.asia.l.to_numpy()[k])


def _window(mk: Market, a_ns: int, b_ns: int) -> tuple[float, float] | None:
    i, j = mk.idx(a_ns), mk.idx(b_ns)
    if j <= i:
        return None
    return float(mk.mid["l"][i:j].min()), float(mk.mid["h"][i:j].max())


@dataclass(frozen=True)
class Target:
    name: str
    price: float
    unit: float
    reward: float

    @property
    def rr(self) -> float:
        return self.reward / self.unit


@dataclass
class TargetSearch:
    target: Target | None
    candidates: list[dict[str, float | str | bool]] = field(default_factory=list)


def select_target(
    mk: Market,
    lv: DayLevels,
    side: int,
    entry: float,
    stop: float,
    placement_ns: int,
    min_rr: float,
    slippage: float,
    commission: float,
) -> TargetSearch:
    """D13: nearest eligible untouched PDH/PDL/NWOG boundary beyond entry with >= min_rr after costs."""
    out = TargetSearch(None)
    cands: list[tuple[float, str, float]] = []
    pd_win = _window(mk, lv.session_start_ns, placement_ns)
    for name, lvl in (("PDH", lv.pdh), ("PDL", lv.pdl)):
        touched = pd_win is not None and pd_win[0] <= lvl <= pd_win[1]
        beyond = (lvl - entry) * side > 0
        out.candidates.append(
            {"name": name, "price": lvl, "touched": touched, "beyond_entry": beyond}
        )
        if beyond and not touched:
            cands.append((abs(lvl - entry), name, lvl))
    if not math.isnan(lv.nwog_lo):
        w = _window(mk, lv.nwog_start_ns, placement_ns)
        touched = (
            w is not None and w[0] < lv.nwog_hi and w[1] > lv.nwog_lo
        )  # traded into the open gap
        name, lvl = ("NWOG_LO", lv.nwog_lo) if side == 1 else ("NWOG_HI", lv.nwog_hi)
        beyond = (lvl - entry) * side > 0
        out.candidates.append(
            {"name": name, "price": lvl, "touched": touched, "beyond_entry": beyond}
        )
        if beyond and not touched:
            cands.append((abs(lvl - entry), name, lvl))
    unit = r_unit(entry, stop, slippage, commission)
    for _, name, lvl in sorted(cands):
        reward = est_reward(entry, lvl, commission)
        if reward >= min_rr * unit:
            out.target = Target(name, lvl, unit, reward)
            break
    return out
