"""Cycle 20 — Silver Bullet v5 (pre-reg 4d802da): v4 + SMT divergence + OTE 70.5% entry + IPDA 20/40/60 levels.

Reuses the cycle 17-19 building blocks (bars, day table, fills, exits, costs, luck test).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.setups import c17_silver_bullet as base
from v17.setups.c17_silver_bullet import (
    BODY_RATIO_MIN,
    FVG_COST_MULT,
    NY,
    RANGE_ATR_MULT,
    Bars,
    Setup,
    Spec,
    exit_loop,
    net_r,
)

MARKETS = ("USA30IDXUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD", "NZDUSD")
PARTNER = {"USA30IDXUSD": ("USA500IDXUSD", 1), "USDJPY": ("DOLLARIDXUSD", 1), "USDCAD": ("DOLLARIDXUSD", 1),
           "USDCHF": ("DOLLARIDXUSD", 1), "AUDUSD": ("DOLLARIDXUSD", -1), "NZDUSD": ("DOLLARIDXUSD", -1)}
_FX = Spec(0.0002, float("inf"), 0.0, 0.00005, 0.00006)
SPECS = {"USA30IDXUSD": Spec(2.0, float("inf"), 0.0, 0.5, 0.0),
         "USDJPY": Spec(0.02, float("inf"), 0.0, 0.005, 0.006),
         "USDCAD": _FX, "USDCHF": _FX, "AUDUSD": _FX, "NZDUSD": _FX}
MIN_FRAME = {"USA30IDXUSD": 10.0, "USDJPY": 0.15, "USDCAD": 0.0015, "USDCHF": 0.0015,
             "AUDUSD": 0.0015, "NZDUSD": 0.0015}
OTE = 0.705
MIN_RR = 2.0


def slots() -> list[tuple[str, str]]:
    return [(w, m) for w in base.WINDOWS for m in MARKETS]


def ipda_levels(b: Bars) -> pd.DataFrame:
    """PDH/PDL, PWH/PWL (cycle 18) plus 20/40/60-trading-day high/low before each day, and the 20-day midpoint."""
    lv = base.daily_levels(b)
    day = pd.to_datetime(b.ts, unit="ns", utc=True).tz_convert(NY).tz_localize(None).normalize()
    d = pd.DataFrame({"day": day, "h": b.mid_h, "l": b.mid_l})
    g = d[d["day"].dt.dayofweek < 5].groupby("day").agg(h=("h", "max"), l=("l", "min"))
    for n in (20, 40, 60):
        lv[f"h{n}"] = g["h"].shift(1).rolling(n, min_periods=n).max()
        lv[f"l{n}"] = g["l"].shift(1).rolling(n, min_periods=n).min()
    lv["mid20"] = (lv["h20"] + lv["l20"]) / 2
    return lv


def _bounds_ns(day: pd.Timestamp, window: str) -> tuple[int, int, int]:
    (sh, sm), _ = base.WINDOWS[window]
    d0 = pd.Timestamp(day).tz_localize(NY)
    ws = d0 + pd.Timedelta(hours=sh, minutes=sm)
    return d0.value, (ws - pd.Timedelta(minutes=60)).value, ws.value


def smt_ok(pb: Bars, rel: int, side: int, t_day: int, t_ph: int, t_ws: int, t_sweep: int) -> bool:
    """True if the partner FAILS to make the matching extreme between window start and the sweep bar."""
    i_day, i_ph, i_ws = np.searchsorted(pb.ts, [t_day, t_ph, t_ws])
    i_end = int(np.searchsorted(pb.ts, t_sweep, side="right"))
    if i_ws <= i_day or i_ws <= i_ph or i_end <= i_ws:
        return False
    partner_low = (side == 1 and rel == 1) or (side == -1 and rel == -1)
    if partner_low:
        lvl = max(pb.mid_l[i_day:i_ws].min(), pb.mid_l[i_ph:i_ws].min())
        return not bool(pb.mid_l[i_ws:i_end].min() < lvl)
    lvl = min(pb.mid_h[i_day:i_ws].max(), pb.mid_h[i_ph:i_ws].max())
    return not bool(pb.mid_h[i_ws:i_end].max() > lvl)


def find_setup_v5(b: Bars, d: pd.Series, lv: pd.Series, sp: Spec, frame: float, window: str,
                  pb: Bars, rel: int) -> Setup | None:
    i_day, i_ph, ws, we = int(d.i_day), int(d.i_ph), int(d.i_ws), int(d.i_we)
    if not np.isfinite(lv.mid20):
        return None
    # 1. IPDA draw
    hi_b, lo_b, px = b.mid_h[i_day:ws].max(), b.mid_l[i_day:ws].min(), b.mid_o[ws]
    cands = []
    for col in ("pdh", "pwh", "h20", "h40", "h60", "pdl", "pwl", "l20", "l40", "l60"):
        v = lv[col]
        is_high = col in ("pdh", "pwh", "h20", "h40", "h60")
        if not np.isfinite(v) or (is_high and hi_b > v) or ((not is_high) and lo_b < v):
            continue
        if (is_high and v > px) or ((not is_high) and v < px):
            cands.append((abs(v - px), v))
    if not cands:
        return None
    draw = min(cands)[1]
    side = 1 if draw > px else -1
    # 2. sweep
    if side == 1:
        lvl = max(b.mid_l[i_day:ws].min(), b.mid_l[i_ph:ws].min())
        hits = np.flatnonzero(b.mid_l[ws:we] < lvl)
    else:
        lvl = min(b.mid_h[i_day:ws].max(), b.mid_h[i_ph:ws].max())
        hits = np.flatnonzero(b.mid_h[ws:we] > lvl)
    if len(hits) == 0:
        return None
    sw = ws + int(hits[0])
    # 3. SMT
    t_day, t_ph, t_ws = _bounds_ns(d.day, window)
    if not smt_ok(pb, rel, side, t_day, t_ph, t_ws, int(b.ts[sw])):
        return None
    # 4. MSS + displacement FVG (v4)
    ref = None
    for j in range(sw - 2, i_day, -1):
        if side == 1 and b.mid_h[j] > b.mid_h[j - 1] and b.mid_h[j] > b.mid_h[j + 1]:
            ref = b.mid_h[j]
            break
        if side == -1 and b.mid_l[j] < b.mid_l[j - 1] and b.mid_l[j] < b.mid_l[j + 1]:
            ref = b.mid_l[j]
            break
    if ref is None:
        return None
    mss = next((m for m in range(sw + 1, we) if (b.mid_c[m] > ref if side == 1 else b.mid_c[m] < ref)), None)
    if mss is None:
        return None
    for c3 in range(sw + 1, min(mss + 1, we - 1) + 1):
        c2, c1 = c3 - 1, c3 - 2
        if c2 < sw or c2 > mss or c3 >= we or not np.isfinite(b.atr[c1]):
            continue
        top, bot = (b.mid_l[c3], b.mid_h[c1]) if side == 1 else (b.mid_l[c1], b.mid_h[c3])
        if not top > bot:
            continue
        rng = b.mid_h[c2] - b.mid_l[c2]
        if rng <= 0 or abs(b.mid_c[c2] - b.mid_o[c2]) / rng < BODY_RATIO_MIN or rng < RANGE_ATR_MULT * b.atr[c1]:
            continue
        if top - bot < FVG_COST_MULT * (b.ask_c[c3] - b.bid_c[c3]):
            continue
        # 6. OTE on the displacement leg
        last = max(c3, mss)
        lo, hi = b.mid_l[sw:last + 1].min(), b.mid_h[sw:last + 1].max()
        if side == 1:
            entry, stop = hi - OTE * (hi - lo), lo - sp.buf_min
        else:
            entry, stop = lo + OTE * (hi - lo), hi + sp.buf_min
        # 5. 20-day location
        if (side == 1 and not entry < lv.mid20) or (side == -1 and not entry > lv.mid20):
            return None
        dist = max((entry - stop) * side, sp.buf_min)
        tp_dist = (draw - entry) * side
        if tp_dist < frame or tp_dist / dist < MIN_RR:
            return None
        return Setup(side, sw, last, entry, entry - side * dist, draw, dist, tp_dist / dist)
    return None


def run_slot_v5(b: Bars, days: pd.DataFrame, market: str, window: str, pb: Bars) -> pd.DataFrame:
    sp, frame = SPECS[market], MIN_FRAME[market]
    rel = PARTNER[market][1]
    lv_all = ipda_levels(b)
    rows = []
    for _, d in days.iterrows():
        if d.day not in lv_all.index:
            continue
        s = find_setup_v5(b, d, lv_all.loc[d.day], sp, frame, window, pb, rel)
        if s is None:
            continue
        fill = next((k for k in range(s.c3 + 1, int(d.i_exp))
                     if (s.side == 1 and b.ask_l[k] <= s.ce) or (s.side == -1 and b.bid_h[k] >= s.ce)), -1)
        if fill < 0:
            continue
        x, reason, px = exit_loop(fill, int(d.i_hard), s.side, s.sl, s.tp, b.bid_l, b.bid_h, b.bid_c,
                                  b.ask_l, b.ask_h, b.ask_c)
        rows.append({"day": d.day, "side": s.side, "sweep_i": s.sweep_i, "placed_after": s.c3, "fill_i": fill,
                     "exit_i": x, "reason": int(reason), "entry": s.ce, "sl": s.sl, "tp": s.tp, "dist": s.dist,
                     "tp_dist": abs(s.tp - s.ce), "rr": s.rr, "r": net_r(s.side, s.ce, px, reason, s.dist, sp)})
    return pd.DataFrame(rows)
