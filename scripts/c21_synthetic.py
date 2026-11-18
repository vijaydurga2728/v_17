"""Deterministic synthetic M1 bid/ask markets for the cycle 21 differential check (no real market data).

Weekly schedule like index CFDs: Sunday 18:00 -> Friday 17:00 NY with a 17:00-18:00 break Mon-Thu, bars on
XNYS holidays too (R29), random weekend gaps (NWOG), and injected faults: one crossed-quote session (R27), one
frozen-ask run (R31), missing minutes inside 09:30-11:05 (R20), repeated provider bars (R30) and opening gaps
through stops (R15). A correlated partner market supports the SMT variant.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"


def _minutes(start: str, end: str) -> pd.DatetimeIndex:
    idx = pd.date_range(f"{start} 00:00", f"{end} 23:59", freq="1min", tz=NY)
    wall = idx.tz_localize(None)
    dow, hour = wall.dayofweek, wall.hour
    keep = (dow < 4) | ((dow == 4) & (hour < 17)) | ((dow == 6) & (hour >= 18))
    keep &= ~((dow < 4) & (hour == 17))  # daily break 17:00-18:00
    return idx[keep]


def generate(
    start: str,
    end: str,
    seed: int,
    partner_seed: int | None = None,
    rho: float = 0.8,
    base: float = 15000.0,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    idx = _minutes(start, end)
    n = len(idx)
    rng = np.random.default_rng(seed)
    wall = idx.tz_localize(None)
    mins = wall.hour * 60 + wall.minute
    # quiet overnight, active 10:00-11:00 (so references survive until the window and sweeps/MSS/FVGs occur)
    vol = np.select(
        [
            (mins >= 600) & (mins < 660),
            (mins >= 570) & (mins < 600),
            (mins >= 660) & (mins < 960),
            mins >= 1200,
        ],
        [7.0, 0.5, 2.5, 1.0],
        default=0.12,
    )
    z = rng.standard_normal(n)
    zp = None
    if partner_seed is not None:
        e = np.random.default_rng(partner_seed).standard_normal(n)
        zp = rho * z + np.sqrt(1 - rho**2) * e
    gaps = np.zeros(n)
    t = idx.asi8
    jump_at = np.flatnonzero(np.diff(t) > 60_000_000_000) + 1  # first bar after a break/weekend
    gaps[jump_at] = rng.normal(0, 4.0, len(jump_at))
    trend = np.repeat(rng.normal(0, 0.03, n // 1380 + 1), 1380)[
        :n
    ]  # slow day-scale drift -> daily structure

    def build(zz: np.ndarray, scale: float, r: np.random.Generator) -> pd.DataFrame:
        step = zz * vol * scale + trend * scale + gaps * scale
        c = base * scale + np.cumsum(step)
        o = (
            np.r_[c[0], c[:-1]] + gaps * scale * 0
        )  # open = previous close (gap already inside step)
        o[jump_at] = c[jump_at - 1] + gaps[jump_at] * scale  # opening gap prints at the open
        hi = np.maximum(o, c) + np.abs(r.standard_normal(n)) * vol * scale * 0.5
        lo = np.minimum(o, c) - np.abs(r.standard_normal(n)) * vol * scale * 0.5
        spread = 1.0 * scale + np.abs(r.standard_normal(n)) * 0.2 * scale
        df = pd.DataFrame({"ts_utc": t})
        for f, m in zip("ohlc", (o, hi, lo, c), strict=True):
            df[f"bid_{f}"], df[f"ask_{f}"] = (
                np.round(m - spread / 2, 2),
                np.round(m + spread / 2, 2),
            )
        return df

    prim = build(z, 1.0, np.random.default_rng(seed + 1))
    part = build(zp, 0.3, np.random.default_rng(seed + 2)) if zp is not None else None
    return _inject_faults(prim, idx, seed), part


def _inject_faults(df: pd.DataFrame, idx: pd.DatetimeIndex, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 99)
    wall = idx.tz_localize(None)
    days = sorted(set(wall.normalize()[(wall.dayofweek < 4)]))
    df = df.copy()
    # R27: one crossed-quote bar in the evening of a day (its next trading date session gets excluded)
    d = days[len(days) // 3]
    k = int(np.flatnonzero((wall.normalize() == d) & (wall.hour == 21))[0])
    df.loc[k, ["ask_o", "ask_h", "ask_l", "ask_c"]] = df.loc[k, "bid_l"] - 1.0
    # R31: frozen ask for 200 bars on another day
    d = days[2 * len(days) // 3]
    k = int(np.flatnonzero((wall.normalize() == d) & (wall.hour == 3))[0])
    df.loc[k : k + 199, ["ask_o", "ask_h", "ask_l", "ask_c"]] = df.bid_h[k : k + 200].max() + 5.0
    # R30: repeated bars (copy previous bar) at random positions
    rep = rng.choice(np.arange(1, len(df)), size=len(df) // 200, replace=False)
    cols = [c for c in df.columns if c != "ts_utc"]
    for r in sorted(rep):
        df.loc[r, cols] = df.loc[r - 1, cols].to_numpy()
    # keep OHLC bounds valid after edits
    for s in ("bid", "ask"):
        df[f"{s}_h"] = df[[f"{s}_o", f"{s}_h", f"{s}_l", f"{s}_c"]].max(axis=1)
        df[f"{s}_l"] = df[[f"{s}_o", f"{s}_h", f"{s}_l", f"{s}_c"]].min(axis=1)
    # R20: delete a few minutes inside 09:30-11:05 on random days
    mins = wall.hour * 60 + wall.minute
    win = np.flatnonzero((mins >= 570) & (mins < 665))
    drop = rng.choice(win, size=12, replace=False)
    return df.drop(index=drop).reset_index(drop=True)
