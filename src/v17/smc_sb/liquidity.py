"""PDH/PDL (R18, R29), Asian range (D2, R5), NWOG (D13 / R19) and target selection (D13 / R17 / R18)."""

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
    pd_created_ns: int  # 17:00 NY on the date of the previous XNYS session (R18)
    asia_h: float
    asia_l: float
    asia_created_ns: int  # 00:00 NY of the trading date (range complete)
    nwog_lo: float
    nwog_hi: float
    nwog_start_ns: int  # Sunday 18:00 NY


def nwog(mk: Market, day: dt.date) -> tuple[float, float, int]:
    """R19: (lo, hi, start_ns) of the current week's NWOG; NaNs when absent or zero-width.

    Friday close = last mid close of a bar starting in [Thursday 17:00, Friday 17:00) NY.
    Sunday open  = first mid open of a bar starting in [Sunday 18:00, Monday 17:00) NY.
    A missing bar on either side => NWOG absent (no substitution).
    """
    sunday = day - dt.timedelta(days=day.weekday() + 1)
    friday, thursday, monday = (sunday - dt.timedelta(days=k) for k in (2, 3, -1))
    sun_ns = ny_ns(sunday, "18:00")
    j_close = mk.idx(ny_ns(friday, "17:00")) - 1
    j_open = mk.idx(sun_ns)
    if j_close < 0 or int(mk.ts[j_close]) < ny_ns(thursday, "17:00"):
        return NAN, NAN, sun_ns
    if j_open >= len(mk.ts) or int(mk.ts[j_open]) >= ny_ns(monday, "17:00"):
        return NAN, NAN, sun_ns
    a, b = float(mk.mid["c"][j_close]), float(mk.mid["o"][j_open])
    if a == b:
        return NAN, NAN, sun_ns
    return min(a, b), max(a, b), sun_ns


def _asia(mk: Market, key: pd.Timestamp) -> tuple[float, float]:
    k = int(mk.asia.index.get_indexer(pd.DatetimeIndex([key]))[0])
    if k < 0:
        return NAN, NAN
    return float(mk.asia.h.to_numpy()[k]), float(mk.asia.l.to_numpy()[k])


def day_levels(mk: Market, day: dt.date, i: int, rollover_hour: int = 17) -> DayLevels:
    """Levels for the trading date at daily position i (> 0); PDH/PDL from the previous XNYS session."""
    prev = mk.daily.iloc[i - 1]
    prev_date = mk.daily.index[i - 1].date()
    ah, al = _asia(mk, pd.Timestamp(day))
    lo, hi, n_start = nwog(mk, day)
    return DayLevels(
        float(prev.h),
        float(prev.l),
        ny_ns(prev_date, f"{rollover_hour:02d}:00"),
        ah,
        al,
        ny_ns(day, "00:00"),
        lo,
        hi,
        n_start,
    )


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
    contaminated: bool = False
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
    if mk.contaminated(lv.pd_created_ns, placement_ns) or (
        not math.isnan(lv.nwog_lo) and mk.contaminated(lv.nwog_start_ns, placement_ns)
    ):
        out.contaminated = True
        return out
    cands: list[tuple[float, str, float]] = []
    pd_win = _window(mk, lv.pd_created_ns, placement_ns)
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
        )  # strictly inside the gap
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
