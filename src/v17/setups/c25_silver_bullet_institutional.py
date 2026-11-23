"""Cycle 25: Institutional Silver Bullet Engine (Out-of-the-Box Architecture).

Key Architectural Upgrades over Cycle 22:
1. Multi-Timeframe Decoupling: M5 Liquidity Sweep + M5 Displacement MSS + M1 Precision FVG Entry.
2. 50% Consequent Encroachment (CE): Limit order placed at the midpoint of the M1 FVG for superior fill pricing.
3. Open-Drive Window: Adds US Cash Open Drive (09:30 - 10:30 NY) for high-momentum index expansions.
4. Two-Tranche Dynamic Liquidity Exit:
   - Tranche 1 (60%): Closes at 1.5R; Stop Loss moves to Breakeven.
   - Tranche 2 (40%): Closes at 2.5R (seeking Draw on Liquidity).
   - Combined Net R is computed with zero lookahead.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from numba import njit

NY = ZoneInfo("America/New_York")
MIN_NS: Final[int] = 60 * 1_000_000_000
M5_NS: Final[int] = 5 * MIN_NS

WINDOWS: Final[dict[str, tuple[tuple[int, int], tuple[int, int]]]] = {
    "OPEN_DRIVE": ((9, 30), (10, 30)), # Index Cash Open Drive
    "AM": ((10, 0), (11, 0)),          # Classic NY AM Silver Bullet
    "PM": ((14, 0), (15, 0)),          # Classic NY PM Silver Bullet
}

SESSION_ENDS: Final[dict[str, tuple[int, int]]] = {
    "OPEN_DRIVE": (16, 30),
    "AM": (16, 30),
    "PM": (16, 30),
}

BODY_RATIO_MIN: Final[float] = 0.55
RANGE_ATR_MULT: Final[float] = 1.10
MIN_RR: Final[float] = 1.50
SPREAD_BUFFER_MULT: Final[float] = 1.50
PIVOT_LEFT: Final[int] = 2
PIVOT_RIGHT: Final[int] = 2


@dataclass(frozen=True)
class Spec:
    min_stop: float
    max_stop: float
    slip: float
    commission_rt: float


SPECS: Final[dict[str, Spec]] = {
    "EURUSD": Spec(min_stop=0.0004, max_stop=0.0030, slip=0.00005, commission_rt=0.00006),
    "USATECHIDXUSD": Spec(min_stop=6.0, max_stop=120.0, slip=0.5, commission_rt=0.0),
    "USA500IDXUSD": Spec(min_stop=1.2, max_stop=25.0, slip=0.5, commission_rt=0.0),
    "USA30IDXUSD": Spec(min_stop=10.0, max_stop=250.0, slip=1.0, commission_rt=0.0),
    "XAUUSD": Spec(min_stop=1.50, max_stop=20.00, slip=0.15, commission_rt=0.0),
}


@dataclass
class Bars:
    ts: np.ndarray       # UTC nanoseconds
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
    atr: np.ndarray


@dataclass
class M5Bars:
    ts_start: np.ndarray
    ts_close: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    atr: np.ndarray
    m1_end_idx: np.ndarray


def prepare(m1: pd.DataFrame) -> Bars:
    m = m1.sort_values("ts_utc").drop_duplicates("ts_utc").reset_index(drop=True)
    f = {k: m[k].to_numpy(np.float64) for k in ("bid_o", "bid_h", "bid_l", "bid_c",
                                                "ask_o", "ask_h", "ask_l", "ask_c")}
    mid = {k: (f[f"bid_{k}"] + f[f"ask_{k}"]) / 2.0 for k in "ohlc"}
    prev_c = np.r_[np.nan, mid["c"][:-1]]
    tr = np.fmax(mid["h"] - mid["l"], np.fmax(np.abs(mid["h"] - prev_c), np.abs(mid["l"] - prev_c)))
    atr = pd.Series(tr).rolling(14, min_periods=14).mean().to_numpy()
    return Bars(m["ts_utc"].to_numpy(np.int64), *f.values(), mid["o"], mid["h"], mid["l"], mid["c"], atr)


def build_m5(b: Bars) -> M5Bars:
    ts_dt = pd.to_datetime(b.ts, unit="ns", utc=True)
    m5_bucket = ts_dt.floor("5min")
    df = pd.DataFrame({
        "bucket": m5_bucket,
        "m1_idx": np.arange(len(b.ts)),
        "o": b.mid_o,
        "h": b.mid_h,
        "l": b.mid_l,
        "c": b.mid_c,
    })
    g = df.groupby("bucket", sort=False).agg(
        o=("o", "first"),
        h=("h", "max"),
        l=("l", "min"),
        c=("c", "last"),
        m1_end=("m1_idx", "last"),
    )
    start_ns = g.index.as_unit("ns").asi8
    close_ns = (g.index + pd.Timedelta(minutes=5)).as_unit("ns").asi8
    o = g["o"].to_numpy(np.float64)
    h = g["h"].to_numpy(np.float64)
    l = g["l"].to_numpy(np.float64)
    c = g["c"].to_numpy(np.float64)
    m1_end = g["m1_end"].to_numpy(np.int64)

    prev_c = np.r_[np.nan, c[:-1]]
    tr = np.fmax(h - l, np.fmax(np.abs(h - prev_c), np.abs(l - prev_c)))
    atr = pd.Series(tr).rolling(14, min_periods=14).mean().to_numpy()
    return M5Bars(start_ns, close_ns, o, h, l, c, atr, m1_end)


@njit(cache=False)
def pivot_flags(h: np.ndarray, l: np.ndarray, left: int = 2, right: int = 2) -> tuple[np.ndarray, np.ndarray]:
    n = len(h)
    ph = np.zeros(n, dtype=np.bool_)
    pl = np.zeros(n, dtype=np.bool_)
    for i in range(left, n - right):
        hi = h[i]
        li = l[i]
        is_h = True
        for j in range(i - left, i):
            if h[j] >= hi:
                is_h = False
                break
        if is_h:
            for j in range(i + 1, i + right + 1):
                if h[j] >= hi:
                    is_h = False
                    break
        ph[i] = is_h

        is_l = True
        for j in range(i - left, i):
            if l[j] <= li:
                is_l = False
                break
        if is_l:
            for j in range(i + 1, i + right + 1):
                if l[j] <= li:
                    is_l = False
                    break
        pl[i] = is_l
    return ph, pl


@njit(cache=False)
def latest_confirmed_pivot(flags: np.ndarray, current_bar: int, right: int = 2) -> int:
    max_pivot_bar = current_bar - right
    for k in range(max_pivot_bar, -1, -1):
        if flags[k]:
            return k
    return -1


@dataclass(frozen=True)
class DayContext:
    pdh: float
    pdl: float
    adr10: float
    asia_h: float
    asia_l: float
    dol_side: int
    adr_exhausted: bool


def build_daily_df(b: Bars) -> pd.DataFrame:
    ts_dt = pd.to_datetime(b.ts, unit="ns", utc=True).tz_convert(NY)
    df = pd.DataFrame({
        "date": ts_dt.date,
        "h": b.mid_h,
        "l": b.mid_l,
        "c": b.mid_c,
    })
    g = df.groupby("date").agg(
        h=("h", "max"),
        l=("l", "min"),
        c=("c", "last"),
    ).reset_index()
    g["range"] = g["h"] - g["l"]
    g["adr10"] = g["range"].shift(1).rolling(10, min_periods=10).mean()
    g["pdh"] = g["h"].shift(1)
    g["pdl"] = g["l"].shift(1)
    return g


def compute_day_context(b: Bars, day_date, window: str, daily_df: pd.DataFrame) -> DayContext | None:
    matched = daily_df[daily_df["date"] == day_date]
    if matched.empty:
        return None
    row = matched.iloc[0]
    pdh, pdl = float(row["pdh"]), float(row["pdl"])
    adr10 = float(row["adr10"])
    if not (np.isfinite(pdh) and np.isfinite(pdl) and np.isfinite(adr10)):
        return None

    (sh, sm), _ = WINDOWS[window]
    day_start_ns = pd.Timestamp(day_date).tz_localize(NY).tz_convert("UTC").value
    ws_ns = day_start_ns + (sh * 3600 + sm * 60) * 1_000_000_000

    i_start = np.searchsorted(b.ts, day_start_ns)
    i_ws = np.searchsorted(b.ts, ws_ns)
    if i_ws <= i_start + 5:
        return None

    intra_h = float(np.max(b.mid_h[i_start:i_ws]))
    intra_l = float(np.min(b.mid_l[i_start:i_ws]))
    intra_range = intra_h - intra_l
    adr_exhausted = intra_range >= 0.80 * adr10

    # Asian reference range: 00:00 to 09:30 NY for AM/OpenDrive, 00:00 to 13:30 NY for PM
    ref_h, ref_m = (13, 30) if window == "PM" else (9, 30)
    ref_ns = day_start_ns + (ref_h * 3600 + ref_m * 60) * 1_000_000_000
    i_ref = np.searchsorted(b.ts, ref_ns)

    if i_ref > i_start:
        asia_h = float(np.max(b.mid_h[i_start:i_ref]))
        asia_l = float(np.min(b.mid_l[i_start:i_ref]))
    else:
        asia_h, asia_l = intra_h, intra_l

    pdl_swept = (intra_l < pdl) or (intra_l < asia_l)
    pdh_swept = (intra_h > pdh) or (intra_h > asia_h)
    cur_px = float(b.mid_c[i_ws - 1])

    if pdl_swept and not pdh_swept:
        dol_side = 1
    elif pdh_swept and not pdl_swept:
        dol_side = -1
    else:
        mid_pd = (pdh + pdl) / 2.0
        dol_side = 1 if cur_px < mid_pd else -1

    return DayContext(pdh, pdl, adr10, asia_h, asia_l, dol_side, adr_exhausted)


@dataclass(frozen=True)
class InstitutionalSetup:
    side: int
    entry_px: float     # 50% Consequent Encroachment (CE) of M1 FVG
    sl_px: float        # Structural Anchor Invalidation
    tp1_px: float       # Tranche 1 (1.5R partial target)
    tp2_px: float       # Tranche 2 (2.5R runner target)
    risk_dist: float
    c_m1_trigger: int   # M1 bar when order placed


def find_institutional_setup(
    b: Bars,
    m5: M5Bars,
    ph5: np.ndarray,
    pl5: np.ndarray,
    m5_start_idx: int,
    m5_end_idx: int,
    ctx: DayContext,
    sp: Spec,
    current_spread: float,
) -> InstitutionalSetup | None:
    if ctx.dol_side == 0 or ctx.adr_exhausted:
        return None

    target_side = ctx.dol_side
    sweep_start = max(0, m5_start_idx - 6)

    for k in range(sweep_start, m5_end_idx):
        if not np.isfinite(m5.atr[k]) or m5.atr[k] <= 0:
            continue

        # 1. M5 Sweep
        if target_side == 1:
            p_idx = latest_confirmed_pivot(pl5, k, right=PIVOT_RIGHT)
            if p_idx < 0 or not (m5.l[k] < m5.l[p_idx]):
                continue
            anchor_px = m5.l[k]
        else:
            p_idx = latest_confirmed_pivot(ph5, k, right=PIVOT_RIGHT)
            if p_idx < 0 or not (m5.h[k] > m5.h[p_idx]):
                continue
            anchor_px = m5.h[k]

        # 2. M5 Displacement & MSS
        disp_start_k2 = max(k + 1, m5_start_idx)
        for k2 in range(disp_start_k2, min(k + 8, m5_end_idx)):
            rng2 = m5.h[k2] - m5.l[k2]
            if rng2 <= 0:
                continue
            body2 = abs(m5.c[k2] - m5.o[k2])
            if body2 / rng2 < BODY_RATIO_MIN:
                continue
            if rng2 < RANGE_ATR_MULT * m5.atr[k2 - 1]:
                continue

            if target_side == 1:
                opp_pivot_idx = latest_confirmed_pivot(ph5, k2, right=PIVOT_RIGHT)
                if opp_pivot_idx < 0 or opp_pivot_idx < k2 - 24 or not (m5.c[k2] > m5.h[opp_pivot_idx]):
                    continue
                anchor_px = min(anchor_px, float(np.min(m5.l[k:k2 + 1])))
            else:
                opp_pivot_idx = latest_confirmed_pivot(pl5, k2, right=PIVOT_RIGHT)
                if opp_pivot_idx < 0 or opp_pivot_idx < k2 - 24 or not (m5.c[k2] < m5.l[opp_pivot_idx]):
                    continue
                anchor_px = max(anchor_px, float(np.max(m5.h[k:k2 + 1])))

            # 3. M1 Precision FVG Search (50% Consequent Encroachment)
            m1_start = int(m5.m1_end_idx[k2 - 1]) if k2 > 0 else 0
            m1_end = min(len(b.mid_o) - 1, int(m5.m1_end_idx[k2]) + 10)

            for m in range(m1_start + 2, m1_end):
                m1 = m - 2
                m3 = m
                if m3 >= len(b.mid_o):
                    break

                if target_side == 1:
                    if not (b.mid_l[m3] > b.mid_h[m1]):
                        continue
                    entry_px = (b.mid_h[m1] + b.mid_l[m3]) / 2.0
                    sl_px = anchor_px - SPREAD_BUFFER_MULT * current_spread
                    risk_dist = entry_px - sl_px
                else:
                    if not (b.mid_h[m3] < b.mid_l[m1]):
                        continue
                    entry_px = (b.mid_l[m1] + b.mid_h[m3]) / 2.0
                    sl_px = anchor_px + SPREAD_BUFFER_MULT * current_spread
                    risk_dist = sl_px - entry_px

                if risk_dist < sp.min_stop or risk_dist > sp.max_stop:
                    continue

                tp1_px = entry_px + target_side * (1.50 * risk_dist)
                tp2_px = entry_px + target_side * (2.50 * risk_dist)

                return InstitutionalSetup(
                    side=target_side,
                    entry_px=entry_px,
                    sl_px=sl_px,
                    tp1_px=tp1_px,
                    tp2_px=tp2_px,
                    risk_dist=risk_dist,
                    c_m1_trigger=m3,
                )

    return None


def simulate_two_tranche_trade(
    b: Bars,
    setup: InstitutionalSetup,
    sp: Spec,
    session_end_m1: int,
) -> tuple[float, int, int]:
    start_m1 = setup.c_m1_trigger + 1
    max_fill_m1 = min(len(b.ts), session_end_m1)
    fill_idx = -1

    for i in range(start_m1, max_fill_m1):
        if setup.side == 1:
            if b.ask_l[i] <= setup.entry_px:
                fill_idx = i
                break
        else:
            if b.bid_h[i] >= setup.entry_px:
                fill_idx = i
                break

    if fill_idx < 0:
        return 0.0, -1, -1

    t1_hit = False
    exit_idx = -1
    r_t1 = 0.0
    r_t2 = 0.0
    current_sl = setup.sl_px

    for i in range(fill_idx + 1, min(len(b.ts), session_end_m1)):
        sl_hit = False
        if setup.side == 1:
            if b.bid_l[i] <= current_sl:
                sl_hit = True
        else:
            if b.ask_h[i] >= current_sl:
                sl_hit = True

        if not t1_hit:
            tp1_hit = False
            if setup.side == 1:
                if b.bid_h[i] >= setup.tp1_px:
                    tp1_hit = True
            else:
                if b.ask_l[i] <= setup.tp1_px:
                    tp1_hit = True

            if sl_hit:
                r_loss = -1.0 - (sp.slip * 2 + sp.commission_rt) / setup.risk_dist
                return r_loss, fill_idx, i

            if tp1_hit:
                t1_hit = True
                r_t1 = 1.50 - (sp.slip * 2 + sp.commission_rt) / setup.risk_dist
                current_sl = setup.entry_px
                continue

        if t1_hit:
            tp2_hit = False
            if setup.side == 1:
                if b.bid_h[i] >= setup.tp2_px:
                    tp2_hit = True
            else:
                if b.ask_l[i] <= setup.tp2_px:
                    tp2_hit = True

            if sl_hit:
                r_t2 = 0.0 - (sp.slip * 2 + sp.commission_rt) / setup.risk_dist
                exit_idx = i
                break

            if tp2_hit:
                r_t2 = 2.50 - (sp.slip * 2 + sp.commission_rt) / setup.risk_dist
                exit_idx = i
                break

    if exit_idx < 0:
        exit_idx = min(len(b.ts) - 1, session_end_m1 - 1)
        cur_px = b.bid_c[exit_idx] if setup.side == 1 else b.ask_c[exit_idx]
        pnl_dist = setup.side * (cur_px - setup.entry_px)
        if not t1_hit:
            r_tot = (pnl_dist - sp.slip * 2 - sp.commission_rt) / setup.risk_dist
            return r_tot, fill_idx, exit_idx
        else:
            r_t2 = (pnl_dist - sp.slip * 2 - sp.commission_rt) / setup.risk_dist

    net_r = 0.60 * r_t1 + 0.40 * r_t2
    return net_r, fill_idx, exit_idx


def run_slot_c25(
    b: Bars,
    symbol: str,
    window_name: str,
    start_date: str,
    end_date: str,
    calendar_df: pd.DataFrame,
) -> pd.DataFrame:
    m5 = build_m5(b)
    ph5, pl5 = pivot_flags(m5.h, m5.l, PIVOT_LEFT, PIVOT_RIGHT)
    daily_df = build_daily_df(b)
    sp = SPECS[symbol]

    (sh, sm), (eh, em) = WINDOWS[window_name]
    (end_h, end_m) = SESSION_ENDS[window_name]

    days = pd.date_range(start_date, end_date, freq="B")
    trades = []

    for day in days:
        d = day.date()
        ctx = compute_day_context(b, d, window_name, daily_df)
        if ctx is None or ctx.dol_side == 0 or ctx.adr_exhausted:
            continue

        d0_ns = pd.Timestamp(d).tz_localize(NY).tz_convert("UTC").value
        ws_ns = d0_ns + (sh * 3600 + sm * 60) * 1_000_000_000
        we_ns = d0_ns + (eh * 3600 + em * 60) * 1_000_000_000
        sess_end_ns = d0_ns + (end_h * 3600 + end_m * 60) * 1_000_000_000

        # Calendar blackout
        if not calendar_df.empty:
            dt_s = calendar_df["timestamp_utc"]
            in_blackout = ((dt_s >= ws_ns - 120 * 1_000_000_000) & (dt_s <= we_ns + 120 * 1_000_000_000)).any()
            if in_blackout:
                continue

        m5_start = int(np.searchsorted(m5.ts_start, ws_ns))
        m5_end = int(np.searchsorted(m5.ts_close, we_ns))
        if m5_end <= m5_start + 2:
            continue

        m1_ws_idx = np.searchsorted(b.ts, ws_ns)
        cur_spread = float(b.ask_c[m1_ws_idx] - b.bid_c[m1_ws_idx]) if m1_ws_idx < len(b.ts) else 0.0001

        setup = find_institutional_setup(b, m5, ph5, pl5, m5_start, m5_end, ctx, sp, cur_spread)
        if not setup:
            continue

        session_end_m1 = int(np.searchsorted(b.ts, sess_end_ns)) - 1
        if session_end_m1 <= setup.c_m1_trigger:
            continue

        net_r, fill_idx, exit_idx = simulate_two_tranche_trade(b, setup, sp, session_end_m1)
        if fill_idx >= 0:
            trades.append({
                "day": str(d),
                "symbol": symbol,
                "window": window_name,
                "side": setup.side,
                "entry": setup.entry_px,
                "sl": setup.sl_px,
                "tp1": setup.tp1_px,
                "tp2": setup.tp2_px,
                "risk_dist": setup.risk_dist,
                "r": net_r,
                "fill_m1": fill_idx,
                "exit_m1": exit_idx,
            })

    return pd.DataFrame(trades)
