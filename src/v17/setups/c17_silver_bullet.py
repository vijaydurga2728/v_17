"""Cycle 17 — ICT Silver Bullet v2 (pre-reg fad6564).

Clean re-implementation with the frozen rulebook values and the cycle 1 bug fixes:
- displacement is tested on FVG candle 2 (the gap-creating candle), not candle 3;
- short exits are checked on the ask side;
- pending CE limit orders expire at window end + 5 min;
- no D1 bias filter: the first sweep inside the window decides long or short.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

try:
    from numba import njit
except ImportError:  # pragma: no cover
    def njit(*a, **k):  # type: ignore[no-redef]
        return (lambda f: f) if not (a and callable(a[0])) else a[0]

NY = "America/New_York"
MIN_NS = 60_000_000_000
BODY_RATIO_MIN = 0.65
RANGE_ATR_MULT = 1.5
ATR_N = 14
FVG_COST_MULT = 2.0
MIN_RR = 1.5
EXPIRY_MIN = 5
HARD_EXIT_MIN = 60

SYMBOLS = ("USATECHIDXUSD", "USA500IDXUSD", "EURUSD", "GBPUSD")
WINDOWS = {"LDN": ((3, 0), (4, 0)), "AM": ((10, 0), (11, 0)), "PM": ((14, 0), (15, 0))}


@dataclass(frozen=True)
class Spec:
    buf_min: float
    buf_max: float
    fallback: float
    slip: float
    commission_rt: float  # price units per unit traded


SPECS = {
    "USATECHIDXUSD": Spec(2.0, 20.0, 15.0, 0.5, 0.0),
    "USA500IDXUSD": Spec(0.6, 6.0, 4.5, 0.5, 0.0),
    "EURUSD": Spec(0.0002, 0.0015, 0.0020, 0.00005, 0.00006),
    "GBPUSD": Spec(0.0002, 0.0015, 0.0020, 0.00005, 0.00006),
}


def slots() -> list[tuple[str, str]]:
    return [(w, s) for w in WINDOWS for s in SYMBOLS]


@dataclass
class Bars:
    ts: np.ndarray
    bid_o: np.ndarray
    bid_h: np.ndarray
    bid_l: np.ndarray
    bid_c: np.ndarray
    ask_o: np.ndarray
    ask_h: np.ndarray
    ask_l: np.ndarray
    ask_c: np.ndarray
    mid_o: np.ndarray
    mid_h: np.ndarray
    mid_l: np.ndarray
    mid_c: np.ndarray
    atr: np.ndarray  # atr[k] = mean true range of the 14 bars ending at k (mid)


def prepare(m1: pd.DataFrame) -> Bars:
    m = m1.sort_values("ts_utc").drop_duplicates("ts_utc")
    f = {k: m[k].to_numpy(np.float64) for k in ("bid_o", "bid_h", "bid_l", "bid_c",
                                               "ask_o", "ask_h", "ask_l", "ask_c")}
    mid = {k: (f[f"bid_{k}"] + f[f"ask_{k}"]) / 2 for k in "ohlc"}
    prev_c = np.r_[np.nan, mid["c"][:-1]]
    tr = np.fmax(mid["h"] - mid["l"], np.fmax(np.abs(mid["h"] - prev_c), np.abs(mid["l"] - prev_c)))
    atr = pd.Series(tr).rolling(ATR_N, min_periods=ATR_N).mean().to_numpy()
    return Bars(m["ts_utc"].to_numpy(np.int64), *f.values(), mid["o"], mid["h"], mid["l"], mid["c"], atr)


def day_table(b: Bars, window: str, start: str, end: str) -> pd.DataFrame:
    """Index boundaries per NY date (weekdays with data) for one window."""
    (sh, sm), (eh, em) = WINDOWS[window]
    days = pd.date_range(start, end, freq="B")
    loc = lambda h, m: pd.DatetimeIndex(days + pd.Timedelta(hours=h, minutes=m)).tz_localize(NY).tz_convert("UTC").as_unit("ns").asi8  # noqa: E731
    ws, we = loc(sh, sm), loc(eh, em)
    t = pd.DataFrame({
        "day": days,
        "i_day": np.searchsorted(b.ts, loc(0, 0)),
        "i_ph": np.searchsorted(b.ts, ws - 60 * MIN_NS),
        "i_ws": np.searchsorted(b.ts, ws),
        "i_we": np.searchsorted(b.ts, we),
        "i_exp": np.searchsorted(b.ts, we + EXPIRY_MIN * MIN_NS),
        "i_hard": np.searchsorted(b.ts, we + HARD_EXIT_MIN * MIN_NS) - 1,
    })
    ok = (t.i_ws > t.i_day) & (t.i_ws > t.i_ph) & (t.i_we > t.i_ws + 3) & (t.i_hard >= t.i_we)
    return t[ok].reset_index(drop=True)


@dataclass(frozen=True)
class Setup:
    side: int
    sweep_i: int
    c3: int
    ce: float
    sl: float
    tp: float
    dist: float
    rr: float


def find_setup(b: Bars, d: pd.Series, sp: Spec) -> Setup | None:
    i_day, i_ph, ws, we = int(d.i_day), int(d.i_ph), int(d.i_ws), int(d.i_we)
    s_hi, s_lo = b.mid_h[i_day:ws].max(), b.mid_l[i_day:ws].min()
    p_hi, p_lo = b.mid_h[i_ph:ws].max(), b.mid_l[i_ph:ws].min()
    low_lvl, high_lvl = max(s_lo, p_lo), min(s_hi, p_hi)  # "either pool" = the nearer one
    side, sweep_i = 0, -1
    for i in range(ws, we):
        lo, hi = b.mid_l[i] < low_lvl, b.mid_h[i] > high_lvl
        if lo and hi:
            return None
        if lo or hi:
            side, sweep_i = (1 if lo else -1), i
            break
    if side == 0:
        return None
    ext = b.mid_l[sweep_i] if side == 1 else b.mid_h[sweep_i]
    for c3 in range(sweep_i + 1, we):
        ext = min(ext, b.mid_l[c3]) if side == 1 else max(ext, b.mid_h[c3])
        c2, c1 = c3 - 1, c3 - 2
        if c2 < sweep_i or not np.isfinite(b.atr[c1]):
            continue
        if side == 1:
            top, bot = b.mid_l[c3], b.mid_h[c1]
        else:
            top, bot = b.mid_l[c1], b.mid_h[c3]
        if not top > bot:
            continue
        rng = b.mid_h[c2] - b.mid_l[c2]
        if rng <= 0 or abs(b.mid_c[c2] - b.mid_o[c2]) / rng < BODY_RATIO_MIN or rng < RANGE_ATR_MULT * b.atr[c1]:
            continue
        if top - bot < FVG_COST_MULT * (b.ask_c[c3] - b.bid_c[c3]):
            continue
        ce = (top + bot) / 2
        if side == 1:
            dist = ce - (ext - sp.buf_min)
            highs = [x for x in (s_hi, p_hi) if x > ce]
            tp = min(highs) if highs else ce + sp.fallback
        else:
            dist = (ext + sp.buf_min) - ce
            lows = [x for x in (s_lo, p_lo) if x < ce]
            tp = max(lows) if lows else ce - sp.fallback
        if dist > sp.buf_max:
            continue
        dist = max(dist, sp.buf_min)
        rr = abs(tp - ce) / dist
        if rr < MIN_RR:
            continue
        return Setup(side, sweep_i, c3, ce, ce - side * dist, tp, dist, rr)
    return None


@njit(cache=False)
def exit_loop(start: int, hard: int, side: int, sl: float, tp: float,
              bid_l: np.ndarray, bid_h: np.ndarray, bid_c: np.ndarray,
              ask_l: np.ndarray, ask_h: np.ndarray, ask_c: np.ndarray) -> tuple[int, int, float]:
    """From the fill bar (only SL checked there) to the hard-exit bar.
    Returns (exit_bar, reason 1=SL 2=TP 3=TIME, raw exit price before slippage)."""
    for k in range(start, hard + 1):
        if side == 1:
            if bid_l[k] <= sl:
                return k, 1, sl
            if k > start and bid_h[k] >= tp:
                return k, 2, tp
        else:
            if ask_h[k] >= sl:
                return k, 1, sl
            if k > start and ask_l[k] <= tp:
                return k, 2, tp
    return hard, 3, (bid_c[hard] if side == 1 else ask_c[hard])


def net_r(side: int, entry: float, exit_px: float, reason: int, dist: float, sp: Spec) -> float:
    slip = sp.slip if reason != 2 else 0.0
    px = exit_px - slip if side == 1 else exit_px + slip
    pnl = (px - entry) * side - sp.commission_rt
    return pnl / dist


def run_slot(b: Bars, days: pd.DataFrame, sp: Spec) -> pd.DataFrame:
    rows = []
    for _, d in days.iterrows():
        s = find_setup(b, d, sp)
        if s is None:
            continue
        fill = -1
        for k in range(s.c3 + 1, int(d.i_exp)):
            if (s.side == 1 and b.ask_l[k] <= s.ce) or (s.side == -1 and b.bid_h[k] >= s.ce):
                fill = k
                break
        if fill < 0:
            continue
        x, reason, px = exit_loop(fill, int(d.i_hard), s.side, s.sl, s.tp, b.bid_l, b.bid_h, b.bid_c,
                                  b.ask_l, b.ask_h, b.ask_c)
        rows.append({"day": d.day, "side": s.side, "sweep_i": s.sweep_i, "c3": s.c3, "fill_i": fill,
                     "exit_i": x, "reason": int(reason), "entry": s.ce, "sl": s.sl, "tp": s.tp,
                     "dist": s.dist, "tp_dist": abs(s.tp - s.ce), "rr": s.rr,
                     "r": net_r(s.side, s.ce, px, reason, s.dist, sp)})
    return pd.DataFrame(rows)


@njit(cache=False)
def _null_core(n_perms: int, seed_keys: np.ndarray, ws: np.ndarray, we: np.ndarray, hard: np.ndarray,
               sides: np.ndarray, dists: np.ndarray, tpds: np.ndarray, slip: float, comm: float,
               bid_o: np.ndarray, ask_o: np.ndarray, bid_l: np.ndarray, bid_h: np.ndarray, bid_c: np.ndarray,
               ask_l: np.ndarray, ask_h: np.ndarray, ask_c: np.ndarray) -> np.ndarray:
    out = np.empty(n_perms)
    n = len(sides)
    nd = len(ws)
    for p in range(n_perms):
        np.random.seed(seed_keys[p])
        perm_sides = sides[np.random.permutation(n)]
        tot = 0.0
        for t in range(n):
            di = np.random.randint(0, nd)
            e = np.random.randint(ws[di], we[di])
            side = perm_sides[t]
            entry = (ask_o[e] + slip) if side == 1 else (bid_o[e] - slip)
            sl = entry - side * dists[t]
            tp = entry + side * tpds[t]
            x, reason, px = exit_loop(e, hard[di], side, sl, tp, bid_l, bid_h, bid_c, ask_l, ask_h, ask_c)
            s = slip if reason != 2 else 0.0
            px2 = px - s if side == 1 else px + s
            tot += ((px2 - entry) * side - comm) / dists[t]
        out[p] = tot / n
    return out


def luck_test(b: Bars, days: pd.DataFrame, trades: pd.DataFrame, sp: Spec, seed: int,
              n_perms: int = 5_000) -> dict[str, float]:
    keys = np.array([np.random.SeedSequence([seed, j]).generate_state(1)[0] for j in range(n_perms)],
                    dtype=np.int64) % (2**31 - 1)
    null = _null_core(n_perms, keys, days.i_ws.to_numpy(np.int64), days.i_we.to_numpy(np.int64),
                      days.i_hard.to_numpy(np.int64), trades.side.to_numpy(np.int64),
                      trades.dist.to_numpy(np.float64), trades.tp_dist.to_numpy(np.float64),
                      sp.slip, sp.commission_rt, b.bid_o, b.ask_o, b.bid_l, b.bid_h, b.bid_c,
                      b.ask_l, b.ask_h, b.ask_c)
    obs = float(trades.r.mean())
    e = int((null >= obs).sum())
    return {"observed_mean_r": obs, "null_mean_r_median": float(np.median(null)),
            "p_mean_r": (e + 1) / (n_perms + 1), "n_perms": n_perms}


# ---------------------------------------------------------------------------
# Cycle 18 — v3 "ICT's own rules" (pre-reg eb5e2e2)
# ---------------------------------------------------------------------------
MIN_FRAME = {"USATECHIDXUSD": 10.0, "USA500IDXUSD": 10.0, "EURUSD": 0.0015, "GBPUSD": 0.0015}


def daily_levels(b: Bars) -> pd.DataFrame:
    """Per NY date: previous weekday high/low (PDH/PDL) and previous Mon-Fri week high/low (PWH/PWL), mid prices."""
    day = (pd.to_datetime(b.ts, unit="ns", utc=True).tz_convert(NY).tz_localize(None).normalize())
    d = pd.DataFrame({"day": day, "h": b.mid_h, "l": b.mid_l})
    d = d[d["day"].dt.dayofweek < 5]
    g = d.groupby("day").agg(h=("h", "max"), l=("l", "min"))
    g["pdh"], g["pdl"] = g["h"].shift(1), g["l"].shift(1)
    wk = g.index.to_period("W-SUN")
    w = g.groupby(wk).agg(wh=("h", "max"), wl=("l", "min"))
    w["pwh"], w["pwl"] = w["wh"].shift(1), w["wl"].shift(1)
    g["pwh"] = w["pwh"].reindex(wk).to_numpy()
    g["pwl"] = w["pwl"].reindex(wk).to_numpy()
    return g[["pdh", "pdl", "pwh", "pwl"]]


def find_setup_v3(b: Bars, d: pd.Series, lv: pd.Series, sp: Spec, min_frame: float,
                  stop_mode: str = "c1") -> Setup | None:
    """stop_mode 'c1' = cycle 18 (beyond FVG candle 1); 'swing' = cycle 18b stop A (window swing)."""
    i_day, ws, we = int(d.i_day), int(d.i_ws), int(d.i_we)
    hi_before, lo_before = b.mid_h[i_day:ws].max(), b.mid_l[i_day:ws].min()
    px = b.mid_o[ws]
    cands = []
    for lvl, is_high in ((lv.pdh, True), (lv.pwh, True), (lv.pdl, False), (lv.pwl, False)):
        if not np.isfinite(lvl):
            continue
        if (is_high and hi_before > lvl) or ((not is_high) and lo_before < lvl):
            continue  # already traded through before the window
        if (is_high and lvl > px) or ((not is_high) and lvl < px):
            cands.append((abs(lvl - px), lvl))
    if not cands:
        return None
    draw = min(cands)[1]
    side = 1 if draw > px else -1
    for c3 in range(ws + 2, we):
        c1 = c3 - 2
        if side == 1:
            top, bot = b.mid_l[c3], b.mid_h[c1]
        else:
            top, bot = b.mid_l[c1], b.mid_h[c3]
        if not top > bot:
            continue
        ce = (top + bot) / 2
        if (draw - ce) * side < min_frame:
            continue
        if stop_mode == "swing":
            stop = (b.mid_l[ws:c1 + 1].min() - sp.buf_min if side == 1
                    else b.mid_h[ws:c1 + 1].max() + sp.buf_min)
        else:
            stop = b.mid_l[c1] - sp.buf_min if side == 1 else b.mid_h[c1] + sp.buf_min
        dist = max((ce - stop) * side, sp.buf_min)
        return Setup(side, ws, c3, ce, ce - side * dist, draw, dist, abs(draw - ce) / dist)
    return None


def run_slot_v3(b: Bars, days: pd.DataFrame, sp: Spec, symbol: str, stop_mode: str = "c1") -> pd.DataFrame:
    lv_all = daily_levels(b)
    rows = []
    for _, d in days.iterrows():
        if d.day not in lv_all.index:
            continue
        s = find_setup_v3(b, d, lv_all.loc[d.day], sp, MIN_FRAME[symbol], stop_mode)
        if s is None:
            continue
        fill = -1
        for k in range(s.c3 + 1, int(d.i_exp)):
            if (s.side == 1 and b.ask_l[k] <= s.ce) or (s.side == -1 and b.bid_h[k] >= s.ce):
                fill = k
                break
        if fill < 0:
            continue
        x, reason, px = exit_loop(fill, int(d.i_hard), s.side, s.sl, s.tp, b.bid_l, b.bid_h, b.bid_c,
                                  b.ask_l, b.ask_h, b.ask_c)
        rows.append({"day": d.day, "side": s.side, "c3": s.c3, "fill_i": fill, "exit_i": x,
                     "reason": int(reason), "entry": s.ce, "sl": s.sl, "tp": s.tp, "dist": s.dist,
                     "tp_dist": abs(s.tp - s.ce), "rr": s.rr,
                     "r": net_r(s.side, s.ce, px, reason, s.dist, sp)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Cycle 19 — v4 full ICT sequence (pre-reg c4461e8)
# ---------------------------------------------------------------------------
V4_MIN_RR = 2.0


def _draw(b: Bars, i_day: int, ws: int, lv: pd.Series) -> tuple[int, float] | None:
    hi_before, lo_before = b.mid_h[i_day:ws].max(), b.mid_l[i_day:ws].min()
    px = b.mid_o[ws]
    cands = []
    for lvl, is_high in ((lv.pdh, True), (lv.pwh, True), (lv.pdl, False), (lv.pwl, False)):
        if not np.isfinite(lvl):
            continue
        if (is_high and hi_before > lvl) or ((not is_high) and lo_before < lvl):
            continue
        if (is_high and lvl > px) or ((not is_high) and lvl < px):
            cands.append((abs(lvl - px), lvl))
    if not cands:
        return None
    draw = min(cands)[1]
    return (1 if draw > px else -1), draw


def find_setup_v4(b: Bars, d: pd.Series, lv: pd.Series, sp: Spec, min_frame: float) -> Setup | None:
    i_day, i_ph, ws, we = int(d.i_day), int(d.i_ph), int(d.i_ws), int(d.i_we)
    dr = _draw(b, i_day, ws, lv)
    if dr is None or not (np.isfinite(lv.pdh) and np.isfinite(lv.pdl)):
        return None
    side, draw = dr
    # 2. sweep of the nearer session / previous-hour pool on the draw's opposite side
    if side == 1:
        lvl = max(b.mid_l[i_day:ws].min(), b.mid_l[i_ph:ws].min())
        hits = np.flatnonzero(b.mid_l[ws:we] < lvl)
    else:
        lvl = min(b.mid_h[i_day:ws].max(), b.mid_h[i_ph:ws].max())
        hits = np.flatnonzero(b.mid_h[ws:we] > lvl)
    if len(hits) == 0:
        return None
    sw = ws + int(hits[0])
    # 3. most recent ICT short-term high/low fully formed before the sweep, then close-confirmed MSS
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
    # 4. first displacement FVG with candle 2 in [sweep, MSS]
    mid_pd = (lv.pdh + lv.pdl) / 2
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
        ce = (top + bot) / 2
        # 5. premium / discount
        if (side == 1 and not ce < mid_pd) or (side == -1 and not ce > mid_pd):
            return None
        # 6. order placed after max(c3, MSS); stop beyond sweep extreme extended to placement
        last = max(c3, mss)
        ext = b.mid_l[sw:last + 1].min() if side == 1 else b.mid_h[sw:last + 1].max()
        stop = ext - sp.buf_min if side == 1 else ext + sp.buf_min
        dist = max((ce - stop) * side, sp.buf_min)
        tp_dist = (draw - ce) * side
        if tp_dist < min_frame or tp_dist / dist < V4_MIN_RR:
            return None
        return Setup(side, sw, last, ce, ce - side * dist, draw, dist, tp_dist / dist)
    return None


def run_slot_v4(b: Bars, days: pd.DataFrame, sp: Spec, symbol: str) -> pd.DataFrame:
    lv_all = daily_levels(b)
    rows = []
    for _, d in days.iterrows():
        if d.day not in lv_all.index:
            continue
        s = find_setup_v4(b, d, lv_all.loc[d.day], sp, MIN_FRAME[symbol])
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
                     "tp_dist": abs(s.tp - s.ce), "rr": s.rr,
                     "r": net_r(s.side, s.ce, px, reason, s.dist, sp)})
    return pd.DataFrame(rows)
