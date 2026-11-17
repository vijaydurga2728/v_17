"""Cycle 15 — IBS mean reversion, long + short (pre-reg a1588e1).

Signal on bar i's close from mid IBS; entry at bar i+1's open; exit per setting.
Each trade's outcome depends only on its own signal bar, so the same function
serves the sequential engine and the random-entry luck-test pool.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

R_UNIT_FRAC = 0.01
MAX_HOLD_EXTRA = 4  # ibs_cross: exit no later than entry bar + 4 (5 bars in the trade)


@dataclass(frozen=True)
class Setting:
    lo: float
    hi: float
    exit: str  # "next_close" | "ibs_cross"


MENU: tuple[Setting, ...] = (
    Setting(0.1, 0.9, "next_close"), Setting(0.1, 0.9, "ibs_cross"),
    Setting(0.2, 0.8, "next_close"), Setting(0.2, 0.8, "ibs_cross"),
)


@dataclass
class Prepared:
    d1: pd.DataFrame
    day_ns: np.ndarray
    mid_c: np.ndarray
    ibs: np.ndarray
    bid_o: np.ndarray
    ask_o: np.ndarray
    bid_c: np.ndarray
    ask_c: np.ndarray


def prepare(d1: pd.DataFrame) -> Prepared:
    d = d1.reset_index(drop=True)
    mid = {k: ((d[f"bid_{k}"] + d[f"ask_{k}"]) / 2).to_numpy(dtype=np.float64) for k in "ohlc"}
    rng = mid["h"] - mid["l"]
    with np.errstate(invalid="ignore", divide="ignore"):
        ibs = np.where(rng > 0, (mid["c"] - mid["l"]) / rng, np.nan)
    return Prepared(d, pd.to_datetime(d["day"]).to_numpy(dtype="datetime64[ns]").astype(np.int64),
                    mid["c"], ibs, d["bid_o"].to_numpy(float), d["ask_o"].to_numpy(float),
                    d["bid_c"].to_numpy(float), d["ask_c"].to_numpy(float))


def signal(p: Prepared, i: int, s: Setting) -> int:
    v = p.ibs[i]
    if not np.isfinite(v):
        return 0
    if v < s.lo:
        return 1
    if v > s.hi:
        return -1
    return 0


def eligible(p: Prepared, i: int, s: Setting) -> bool:
    """The trade's last possible exit bar must exist in the data."""
    need = 1 + (MAX_HOLD_EXTRA if s.exit == "ibs_cross" else 0)
    return i + need <= len(p.mid_c) - 1


def exit_bar(p: Prepared, i: int, side: int, s: Setting) -> int:
    e = i + 1
    if s.exit == "next_close":
        return e
    for j in range(e, e + MAX_HOLD_EXTRA + 1):
        v = p.ibs[j]
        if np.isfinite(v) and ((side == 1 and v > s.hi) or (side == -1 and v < s.lo)):
            return j
    return e + MAX_HOLD_EXTRA


def outcome(p: Prepared, i: int, side: int, s: Setting) -> tuple[int, float]:
    e, x = i + 1, exit_bar(p, i, side, s)
    ru = R_UNIT_FRAC * p.mid_c[i]
    if side == 1:
        return x, (p.bid_c[x] - p.ask_o[e]) / ru
    return x, (p.bid_o[e] - p.ask_c[x]) / ru


def run(p: Prepared, s: Setting, win_start_ns: int, win_end_ns: int) -> pd.DataFrame:
    n = len(p.mid_c)
    rows = []
    i = 0
    while i < n - 1:
        if p.day_ns[i] < win_start_ns:
            i += 1
            continue
        if p.day_ns[i] >= win_end_ns:
            break
        side = signal(p, i, s)
        if side == 0 or not eligible(p, i, s):
            i += 1
            continue
        x, r = outcome(p, i, side, s)
        rows.append({"signal_i": i, "entry_i": i + 1, "exit_i": x, "side": side,
                     "ts_entry_ns": int(p.day_ns[i + 1]), "exit_day_ns": int(p.day_ns[x]), "pnl_r": r})
        i = x  # a signal on the exit bar itself is allowed (entry at the next open)
    return pd.DataFrame(rows, columns=["signal_i", "entry_i", "exit_i", "side", "ts_entry_ns",
                                       "exit_day_ns", "pnl_r"])


def outcome_table(p: Prepared, s: Setting, win_start_ns: int, win_end_ns: int) -> pd.DataFrame:
    """Long and short R from every eligible bar in the window (luck-test pool)."""
    idx = [i for i in range(len(p.mid_c) - 1)
           if win_start_ns <= p.day_ns[i] < win_end_ns and np.isfinite(p.ibs[i]) and eligible(p, i, s)]
    return pd.DataFrame({"signal_i": idx,
                         "r_long": [outcome(p, i, 1, s)[1] for i in idx],
                         "r_short": [outcome(p, i, -1, s)[1] for i in idx]})
