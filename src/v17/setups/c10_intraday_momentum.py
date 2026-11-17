"""Cycle 10 — market intraday momentum on NAS100 (slots G, B, Z).

Spec: docs/superpowers/specs/2026-11-17-cycle10-intraday-momentum-prereg.md (FROZEN 2e671b9).

Data model: ``DayGrid`` holds one row per full XNYS day with data and 390 minute
columns (09:30 .. 15:59 bar starts). Missing M1 bars are NaN. Minute index ``i``
corresponds to spec minute ``m = i + 1``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from v17.setups.c9_pdh_pdl import NY_TZ, full_rth_days

N_MIN: Final[int] = 390
OPEN_MIN: Final[int] = 9 * 60 + 30
I_1000: Final[int] = 29    # 09:59 bar -> price at 10:00
I_1530_SIG: Final[int] = 359  # 15:29 bar -> price at 15:30
I_1530_ENTRY: Final[int] = 360  # 15:30 bar open = entry
I_LAST: Final[int] = 389   # 15:59 bar close = 16:00
RU_LOOKBACK: Final[int] = 14
SIGMA_LOOKBACK: Final[int] = 14
SIGMA_MIN_PERIODS: Final[int] = 13
Z_CHECKS: Final[tuple[int, ...]] = tuple(m - 1 for m in range(30, 361, 30))  # minute idx 29..359
SLOTS: Final[tuple[str, ...]] = ("G", "B", "Z")  # slot_index order, pre-reg §9
FIELDS: Final[tuple[str, ...]] = (
    "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c",
)


@dataclass
class DayGrid:
    dates: np.ndarray              # (D,) datetime64[D]
    prev_ok: np.ndarray            # (D,) bool: day d-1 is the calendar-previous full day
    px: dict[str, np.ndarray]      # field -> (D, 390); includes mid_o/h/l/c and vol

    @property
    def n_days(self) -> int:
        return len(self.dates)

    def __getitem__(self, k: str) -> np.ndarray:
        return self.px[k]


def build_grid(m1: pd.DataFrame, start: str, end: str) -> DayGrid:
    """Scatter paired M1 into a (day, minute) grid over full XNYS days only."""
    full = full_rth_days(start, end)
    local = (pd.to_datetime(m1["ts_utc"].to_numpy(dtype=np.int64), unit="ns", utc=True)
             .tz_convert(NY_TZ).tz_localize(None).to_numpy())
    day = local.astype("datetime64[D]")
    minute = ((local - day) // np.timedelta64(1, "m")).astype(np.int64) - OPEN_MIN
    keep = (minute >= 0) & (minute < N_MIN) & np.isin(day, full)
    days_present = np.unique(day[keep])
    d_idx = np.searchsorted(days_present, day[keep])
    m_idx = minute[keep]
    px: dict[str, np.ndarray] = {}
    for f in FIELDS:
        g = np.full((len(days_present), N_MIN), np.nan)
        g[d_idx, m_idx] = m1[f].to_numpy(dtype=np.float64)[keep]
        px[f] = g
    vol = np.full((len(days_present), N_MIN), np.nan)
    v = np.zeros(int(keep.sum()))
    for col in ("bid_volume", "ask_volume"):
        if col in m1:
            v = v + m1[col].to_numpy(dtype=np.float64)[keep]
    vol[d_idx, m_idx] = v
    px["vol"] = vol
    for s in "ohlc":
        px[f"mid_{s}"] = (px[f"bid_{s}"] + px[f"ask_{s}"]) / 2
    pos = np.searchsorted(full, days_present)
    prev_ok = np.r_[False, pos[1:] == pos[:-1] + 1] if len(pos) else np.zeros(0, bool)
    return DayGrid(days_present.astype("datetime64[D]"), prev_ok, px)


def prev_close(g: DayGrid) -> np.ndarray:
    """PC(D): 16:00 mid of the previous full day; NaN if that day has no data (pre-reg §4)."""
    c = g["mid_c"][:, I_LAST]
    pc = np.full(g.n_days, np.nan)
    pc[1:] = np.where(g.prev_ok[1:], c[:-1], np.nan)
    return pc


def r_unit_frac(g: DayGrid) -> np.ndarray:
    """mean_{k=1..14} |C(D-k)/O(D-k) - 1| over the previous 14 data days (all must be valid)."""
    oc = np.abs(g["mid_c"][:, I_LAST] / g["mid_o"][:, 0] - 1)
    s = pd.Series(oc).rolling(RU_LOOKBACK, min_periods=RU_LOOKBACK).mean().shift(1)
    return np.asarray(s.to_numpy(), dtype=np.float64)


def sigma_open(g: DayGrid) -> np.ndarray:
    """sigma(D, m) = mean |mid_c(D-k, m)/O(D-k) - 1|, k=1..14, >= 13 valid (pre-reg §8.2)."""
    move = np.abs(g["mid_c"] / g["mid_o"][:, [0]] - 1)
    df = pd.DataFrame(move)
    return df.rolling(SIGMA_LOOKBACK, min_periods=SIGMA_MIN_PERIODS).mean().shift(1).to_numpy()


def vwap(g: DayGrid) -> np.ndarray:
    """Cumulative tick-volume VWAP of typical mid price from 09:30 (pre-reg §8.4)."""
    tp = (g["mid_h"] + g["mid_l"] + g["mid_c"]) / 3
    v = np.nan_to_num(g["vol"], nan=0.0)
    num = np.cumsum(np.where(np.isfinite(tp), tp * v, 0.0), axis=1)
    den = np.cumsum(np.where(np.isfinite(tp), v, 0.0), axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    out[den == 0] = np.nan
    return np.asarray(out, dtype=np.float64)


@dataclass
class TradeArrays:
    """One row per trade. ``r_long``/``r_short`` = net R had the trade been long/short
    (same timestamps, real bid/ask); used by the direction-permutation MCPT."""
    day: np.ndarray
    side: np.ndarray       # +1 long, -1 short
    entry_i: np.ndarray    # minute index of entry bar (filled at its open)
    exit_i: np.ndarray     # minute index of exit (open of that bar, or close of 389 when == 390)
    r_long: np.ndarray
    r_short: np.ndarray

    @property
    def r(self) -> np.ndarray:
        return np.where(self.side == 1, self.r_long, self.r_short)

    def to_frame(self, g: DayGrid) -> pd.DataFrame:
        return pd.DataFrame({
            "date": g.dates[self.day], "side": np.where(self.side == 1, "long", "short"),
            "entry_min": self.entry_i, "exit_min": self.exit_i, "r": self.r,
            "r_long": self.r_long, "r_short": self.r_short,
        })


def _exit_px(g: DayGrid, d: np.ndarray, i: np.ndarray, side: int) -> np.ndarray:
    """Exit price: open of bar i, or close of the 15:59 bar when i == 390 (EOD)."""
    if side == 1:
        at_open, at_close = g["bid_o"], g["bid_c"]
    else:
        at_open, at_close = g["ask_o"], g["ask_c"]
    ii = np.minimum(i, N_MIN - 1)
    return np.where(i >= N_MIN, at_close[d, N_MIN - 1], at_open[d, ii])


def _rs(g: DayGrid, d: np.ndarray, ei: np.ndarray, xi: np.ndarray, ru_frac: np.ndarray,
        slip: float) -> tuple[np.ndarray, np.ndarray]:
    long_in = g["ask_o"][d, ei] + slip
    long_out = _exit_px(g, d, xi, 1) - slip
    short_in = g["bid_o"][d, ei] - slip
    short_out = _exit_px(g, d, xi, -1) + slip
    r_long = (long_out - long_in) / (long_in * ru_frac[d])
    r_short = (short_in - short_out) / (short_in * ru_frac[d])
    return r_long, r_short


def run_last_half_hour(g: DayGrid, slot: str, slip: float = 0.0) -> TradeArrays:
    """Slots G and B (pre-reg §6-7)."""
    if slot not in ("G", "B"):
        raise ValueError(slot)
    pc = prev_close(g)
    sig_i = I_1000 if slot == "G" else I_1530_SIG
    s = g["mid_c"][:, sig_i] / pc - 1
    ru = r_unit_frac(g)
    need = (np.isfinite(s) & (s != 0) & np.isfinite(ru)
            & np.isfinite(g["ask_o"][:, I_1530_ENTRY]) & np.isfinite(g["bid_o"][:, I_1530_ENTRY])
            & np.isfinite(g["ask_c"][:, I_LAST]) & np.isfinite(g["bid_c"][:, I_LAST]))
    d = np.flatnonzero(need)
    ei = np.full(len(d), I_1530_ENTRY)
    xi = np.full(len(d), N_MIN)  # close of 15:59 bar
    rl, rs = _rs(g, d, ei, xi, ru, slip)
    return TradeArrays(d, np.sign(s[d]).astype(np.int64), ei, xi, rl, rs)


def z_signals(g: DayGrid) -> np.ndarray:
    """(D, 12) signals at the Z check minutes: +1, -1, 0 (undefined -> 0)."""
    sig = sigma_open(g)
    vw = vwap(g)
    pc = prev_close(g)
    o = g["mid_o"][:, 0]
    # Bands need both O(D) and PC(D); np.maximum/minimum propagate NaN -> no signal.
    ub_base = np.maximum(o, pc)
    lb_base = np.minimum(o, pc)
    out = np.zeros((g.n_days, len(Z_CHECKS)), dtype=np.int64)
    for k, i in enumerate(Z_CHECKS):
        c = g["mid_c"][:, i]
        ub = ub_base * (1 + sig[:, i])
        lb = lb_base * (1 - sig[:, i])
        with np.errstate(invalid="ignore"):
            up = (c > ub) & (c > vw[:, i])
            dn = (c < lb) & (c < vw[:, i])
        out[:, k] = np.where(up, 1, np.where(dn, -1, 0))
    return out


def z_tradeable_days(g: DayGrid) -> np.ndarray:
    """Pre-reg §5 required bars for Z: every check bar's close, every next-bar open, 15:59 close."""
    chk = np.array(Z_CHECKS)
    ok = np.isfinite(g["mid_c"][:, chk]).all(axis=1)
    ok &= np.isfinite(g["bid_o"][:, chk + 1]).all(axis=1)
    ok &= np.isfinite(g["ask_o"][:, chk + 1]).all(axis=1)
    ok &= np.isfinite(g["bid_c"][:, I_LAST]) & np.isfinite(g["ask_c"][:, I_LAST])
    ok &= np.isfinite(prev_close(g)) & np.isfinite(r_unit_frac(g))
    return np.asarray(ok, dtype=np.bool_)


def run_z(g: DayGrid, slip: float = 0.0) -> TradeArrays:
    """Slot Z state machine (pre-reg §8.6-8.8)."""
    sig = z_signals(g)
    ok = z_tradeable_days(g)
    ru = r_unit_frac(g)
    days, sides, eis, xis = [], [], [], []
    for d in np.flatnonzero(ok):
        pos, entry = 0, -1
        for k, i in enumerate(Z_CHECKS):
            s = int(sig[d, k])
            act = i + 1  # fill at the next bar's open
            if pos not in (0, s):
                days.append(d)
                sides.append(pos)
                eis.append(entry)
                xis.append(act)
                pos = 0
            if pos == 0 and s != 0:
                pos, entry = s, act
        if pos != 0:
            days.append(d)
            sides.append(pos)
            eis.append(entry)
            xis.append(N_MIN)
    d_arr = np.asarray(days, dtype=np.int64)
    ei = np.asarray(eis, dtype=np.int64)
    xi = np.asarray(xis, dtype=np.int64)
    rl, rs = _rs(g, d_arr, ei, xi, ru, slip)
    return TradeArrays(d_arr, np.asarray(sides, dtype=np.int64), ei, xi, rl, rs)


def run_slot(g: DayGrid, slot: str, slip: float = 0.0) -> TradeArrays:
    return run_z(g, slip) if slot == "Z" else run_last_half_hour(g, slot, slip)
