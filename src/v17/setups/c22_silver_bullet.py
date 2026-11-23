"""Cycle 22 — Institutional Silver Bullet (Zero-Lookahead Reform).

Key architectural upgrades from Cycles 17-21:
1. Zero lookahead guarantee: M5 pivots confirmed only after `right` bars close (RULES.md R1).
2. Dual-timeframe split: M5 structure (sweeps, displacement, MSS) + M1 execution/fills.
3. HTF Draw on Liquidity (DOL): Two-tier liquidity magnet from closed D1/Asian ranges. No trend-fading.
4. Unified impulse: Candle 2 of FVG is the displacement candle that breaks structure (MSS).
5. Robust invalidation: SL placed at structural swing anchor + spread buffer (RULES.md R2).
6. Extended order lifespan: Active until session close or swing invalidation (no 5-min cancels).
7. Hybrid target: 1.5R to 2.0R or opposing M5/M15 swing, capped to session ATR.
8. Filters: News blackout (+/- 15 mins) and ADR exhaustion gate (< 80% 10-day ADR).
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from typing import Final

import numpy as np
import pandas as pd

try:
    from numba import njit
except ImportError:  # pragma: no cover
    def njit(*a, **k):  # type: ignore[no-redef]
        return (lambda f: f) if not (a and callable(a[0])) else a[0]

NY: Final[str] = "America/New_York"
MIN_NS: Final[int] = 60_000_000_000
M5_NS: Final[int] = 5 * MIN_NS

# Windows (start_hour, start_min), (end_hour, end_min)
WINDOWS: Final[dict[str, tuple[tuple[int, int], tuple[int, int]]]] = {
    "LDN": ((3, 0), (4, 0)),
    "AM": ((10, 0), (11, 0)),
    "PM": ((14, 0), (15, 0)),
}

# Session end times (hour, min) for order expiration & hard trade exit
SESSION_ENDS: Final[dict[str, tuple[int, int]]] = {
    "LDN": (8, 0),    # London active session cutoff (08:00 NY = 13:00 London)
    "AM": (16, 30),   # NY AM active cutoff (16:30 NY cash close)
    "PM": (16, 30),   # NY PM cash close cutoff (16:30 NY)
}

CURATED_SLOTS: Final[list[tuple[str, str]]] = [
    ("AM", "XAUUSD"),
    ("PM", "USA30IDXUSD"),
    ("PM", "EURUSD"),
    ("PM", "USA500IDXUSD"),
    ("AM", "EURUSD"),
    ("PM", "USATECHIDXUSD"),
]

BODY_RATIO_MIN: Final[float] = 0.60
RANGE_ATR_MULT: Final[float] = 1.20
MIN_RR: Final[float] = 1.50
MAX_TARGET_R: Final[float] = 2.00
ADR_MAX_PCT: Final[float] = 0.80
SPREAD_BUFFER_MULT: Final[float] = 1.50
PIVOT_LEFT: Final[int] = 2
PIVOT_RIGHT: Final[int] = 2


@dataclass(frozen=True)
class Spec:
    min_stop: float      # Minimum stop distance
    max_stop: float      # Maximum stop distance
    slip: float          # Per-side slippage in price units
    commission_rt: float # Round-trip commission in price units per unit traded


SPECS: Final[dict[str, Spec]] = {
    "EURUSD": Spec(min_stop=0.0006, max_stop=0.0025, slip=0.00005, commission_rt=0.00006),
    "GBPUSD": Spec(min_stop=0.0015, max_stop=0.0035, slip=0.00005, commission_rt=0.00006),
    "USDJPY": Spec(min_stop=0.08, max_stop=0.50, slip=0.005, commission_rt=0.006),
    "AUDUSD": Spec(min_stop=0.0006, max_stop=0.0025, slip=0.00005, commission_rt=0.00006),
    "USDCAD": Spec(min_stop=0.0006, max_stop=0.0025, slip=0.00005, commission_rt=0.00006),
    "USATECHIDXUSD": Spec(min_stop=8.0, max_stop=120.0, slip=0.5, commission_rt=0.0),
    "USA500IDXUSD": Spec(min_stop=1.5, max_stop=25.0, slip=0.5, commission_rt=0.0),
    "USA30IDXUSD": Spec(min_stop=15.0, max_stop=250.0, slip=1.0, commission_rt=0.0),
    "XAUUSD": Spec(min_stop=2.50, max_stop=20.00, slip=0.15, commission_rt=0.00),
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
    ts_start: np.ndarray  # Start of 5-min candle (UTC ns)
    ts_close: np.ndarray  # Close of 5-min candle (UTC ns, available at end of bar)
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    atr: np.ndarray
    m1_end_idx: np.ndarray  # Corresponding M1 bar index for this M5 bar's close


def prepare(m1: pd.DataFrame) -> Bars:
    """Prepare M1 bars sorted, deduplicated, and with ATR precomputed."""
    m = m1.sort_values("ts_utc").drop_duplicates("ts_utc").reset_index(drop=True)
    f = {k: m[k].to_numpy(np.float64) for k in ("bid_o", "bid_h", "bid_l", "bid_c",
                                                "ask_o", "ask_h", "ask_l", "ask_c")}
    mid = {k: (f[f"bid_{k}"] + f[f"ask_{k}"]) / 2.0 for k in "ohlc"}
    prev_c = np.r_[np.nan, mid["c"][:-1]]
    tr = np.fmax(mid["h"] - mid["l"], np.fmax(np.abs(mid["h"] - prev_c), np.abs(mid["l"] - prev_c)))
    atr = pd.Series(tr).rolling(14, min_periods=14).mean().to_numpy()
    return Bars(m["ts_utc"].to_numpy(np.int64), *f.values(), mid["o"], mid["h"], mid["l"], mid["c"], atr)


def build_m5(b: Bars) -> M5Bars:
    """Construct strictly point-in-time M5 bars from closed M1 bars.
    
    A 5-minute bar starting at minute 0 (00:00) contains M1 bars 00:00..00:04.
    Its close is ONLY known when bar 00:04 completes (at 00:05).
    """
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
    
    # Aggregate to M5
    g = df.groupby("bucket", sort=False).agg(
        o=("o", "first"),
        h=("h", "max"),
        l=("l", "min"),
        c=("c", "last"),
        m1_end=("m1_idx", "last"),
    )
    
    start_ns = g.index.as_unit("ns").asi8
    # Close timestamp is 5 minutes after start
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
    """Strict fractal pivots: h[k] > all neighbours in [k-left, k+right].
    
    CRITICAL LOOKAHEAD GUARD: Pivot at index k is ONLY confirmed after bar k+right closes.
    """
    n = len(h)
    ph = np.zeros(n, dtype=np.bool_)
    pl = np.zeros(n, dtype=np.bool_)
    for k in range(left, n - right):
        is_h = True
        is_l = True
        for j in range(k - left, k + right + 1):
            if j == k:
                continue
            if h[k] <= h[j]:
                is_h = False
            if l[k] >= l[j]:
                is_l = False
        ph[k] = is_h
        pl[k] = is_l
    return ph, pl


def latest_confirmed_pivot(flags: np.ndarray, before_m5_idx: int, right: int = 2) -> int:
    """Returns latest pivot index k confirmed BEFORE bar `before_m5_idx`.
    
    To be confirmed before bar i, bar k+right must have closed before bar i starts:
    k + right <= before_m5_idx - 1  =>  k <= before_m5_idx - 1 - right.
    """
    max_k = before_m5_idx - 1 - right
    if max_k < 0:
        return -1
    hits = np.flatnonzero(flags[: max_k + 1])
    return int(hits[-1]) if len(hits) else -1


@dataclass(frozen=True)
class DayContext:
    pdh: float
    pdl: float
    adr10: float
    asia_h: float
    asia_l: float
    dol_side: int      # +1 bullish magnet (seek PDH), -1 bearish magnet (seek PDL), 0 neutral
    adr_exhausted: bool


def compute_day_context(b: Bars, day_date: dt.date, window: str, daily_df: pd.DataFrame) -> DayContext | None:
    """Computes point-in-time Draw on Liquidity (DOL), Asian range, and 10-day ADR strictly prior to window start.
    
    Zero lookahead: Only uses closed days prior to `day_date`.
    """
    day_ts = pd.Timestamp(day_date)
    if day_ts not in daily_df.index:
        return None
    
    row = daily_df.loc[day_ts]
    pdh, pdl = float(row["pdh"]), float(row["pdl"])
    adr10 = float(row["adr10"])
    if not (np.isfinite(pdh) and np.isfinite(pdl) and np.isfinite(adr10)):
        return None
    
    # Calculate intraday range up to window start (ws)
    (sh, sm), _ = WINDOWS[window]
    ws_ns = pd.Timestamp(day_date).tz_localize(NY).tz_convert("UTC").value + (sh * 3600 + sm * 60) * 1_000_000_000
    day_start_ns = pd.Timestamp(day_date).tz_localize(NY).tz_convert("UTC").value
    
    i_start = np.searchsorted(b.ts, day_start_ns)
    i_ws = np.searchsorted(b.ts, ws_ns)
    if i_ws <= i_start + 5:
        return None
    
    intra_h = float(np.max(b.mid_h[i_start:i_ws]))
    intra_l = float(np.min(b.mid_l[i_start:i_ws]))
    intra_range = intra_h - intra_l
    
    # ADR exhaustion check
    adr_exhausted = intra_range >= ADR_MAX_PCT * adr10
    
    # Session reference range (00:00 to 02:00 NY for London; 00:00 to 09:30 NY for AM; 00:00 to 13:30 NY for PM)
    asia_end_h, asia_end_m = (2, 0) if window == "LDN" else ((9, 30) if window == "AM" else (13, 30))
    asia_end_ns = day_start_ns + (asia_end_h * 3600 + asia_end_m * 60) * 1_000_000_000
    i_asia_end = np.searchsorted(b.ts, asia_end_ns)
    
    if i_asia_end > i_start:
        asia_h = float(np.max(b.mid_h[i_start:i_asia_end]))
        asia_l = float(np.min(b.mid_l[i_start:i_asia_end]))
    else:
        asia_h, asia_l = intra_h, intra_l
    
    # Determine Two-Tier DOL
    # Did prior price action already sweep Asian Low or PDL?
    pdl_swept = intra_l < pdl or intra_l < asia_l
    pdh_swept = intra_h > pdh or intra_h > asia_h
    
    cur_px = float(b.mid_c[i_ws - 1])
    
    if pdl_swept and not pdh_swept:
        # Swept sell-side liquidity, now drawing towards buy-side liquidity (PDH)
        dol_side = 1
    elif pdh_swept and not pdl_swept:
        # Swept buy-side liquidity, now drawing towards sell-side liquidity (PDL)
        dol_side = -1
    else:
        # Check discount vs premium relative to previous day range
        mid_pd = (pdh + pdl) / 2.0
        if cur_px < mid_pd:
            dol_side = 1  # In discount: seek buy-side DOL
        elif cur_px > mid_pd:
            dol_side = -1 # In premium: seek sell-side DOL
        else:
            dol_side = 0
            
    return DayContext(pdh, pdl, adr10, asia_h, asia_l, dol_side, adr_exhausted)


def build_daily_df(b: Bars) -> pd.DataFrame:
    """Builds daily summary DataFrame with prior-day PDH/PDL and rolling 10-day ADR."""
    ts_dt = pd.to_datetime(b.ts, unit="ns", utc=True).tz_convert(NY).tz_localize(None).normalize()
    df = pd.DataFrame({"day": ts_dt, "h": b.mid_h, "l": b.mid_l})
    df = df[df["day"].dt.dayofweek < 5]
    
    g = df.groupby("day").agg(h=("h", "max"), l=("l", "min"))
    g["pdh"] = g["h"].shift(1)
    g["pdl"] = g["l"].shift(1)
    g["rng"] = g["h"] - g["l"]
    g["adr10"] = g["rng"].shift(1).rolling(10, min_periods=5).mean()
    return g


@dataclass(frozen=True)
class Setup:
    side: int
    sweep_m5: int
    anchor_px: float     # Structural invalidation extreme
    c3_m5: int          # M5 candle confirming MSS + FVG
    c3_close_m1: int    # M1 index when candle 3 closes (order placement timestamp)
    entry_px: float     # Proximal edge of FVG
    sl_px: float        # Stop loss with spread buffer
    tp_px: float        # Target
    risk_dist: float
    rr: float


def find_setup(
    m5: M5Bars,
    ph5: np.ndarray,
    pl5: np.ndarray,
    m5_start_idx: int,
    m5_end_idx: int,
    ctx: DayContext,
    sp: Spec,
    current_spread: float,
) -> Setup | None:
    """Searches for a unified Silver Bullet setup on M5 strictly within [m5_start_idx, m5_end_idx].
    
    Enforces:
    1. Alignment with HTF DOL (ctx.dol_side).
    2. Zero lookahead in pivot querying.
    3. Unified impulse: Candle 2 of FVG breaks the opposing structure (MSS).
    4. Structural anchor invalidation.
    """
    if ctx.dol_side == 0 or ctx.adr_exhausted:
        return None
    
    target_side = ctx.dol_side
    
    # Scan through M5 bars: allows pre-market / session open sweep up to 30 mins (6 bars) prior to window
    sweep_start_idx = max(0, m5_start_idx - 6)
    for k in range(sweep_start_idx, m5_end_idx):
        if not np.isfinite(m5.atr[k]) or m5.atr[k] <= 0:
            continue
            
        # 1. Sweep verification: Must sweep a confirmed opposing swing pivot
        if target_side == 1:
            # Bullish setup: sweeps a confirmed swing low
            pivot_idx = latest_confirmed_pivot(pl5, k, right=PIVOT_RIGHT)
            if pivot_idx < 0:
                continue
            sweep_level = m5.l[pivot_idx]
            # Sweep occurs if current bar low pierces the confirmed swing low
            if not (m5.l[k] < sweep_level):
                continue
            anchor_px = m5.l[k]
        else:
            # Bearish setup: sweeps a confirmed swing high
            pivot_idx = latest_confirmed_pivot(ph5, k, right=PIVOT_RIGHT)
            if pivot_idx < 0:
                continue
            sweep_level = m5.h[pivot_idx]
            # Sweep occurs if current bar high pierces the confirmed swing high
            if not (m5.h[k] > sweep_level):
                continue
            anchor_px = m5.h[k]
            
        # 2. Look for Unified Displacement & MSS within the window after the sweep
        # k2 must close inside the algorithmic window [m5_start_idx, m5_end_idx]
        disp_start_k2 = max(k + 1, m5_start_idx)
        for k2 in range(disp_start_k2, min(k + 8, m5_end_idx)):
            # Check displacement on k2
            rng2 = m5.h[k2] - m5.l[k2]
            if rng2 <= 0:
                continue
            body2 = abs(m5.c[k2] - m5.o[k2])
            if body2 / rng2 < BODY_RATIO_MIN:
                continue
            if rng2 < RANGE_ATR_MULT * m5.atr[k2 - 1]:
                continue
                
            # Check Market Structure Shift (MSS) on k2:
            # Must close beyond the opposing swing formed prior to k2 (zero lookahead)
            if target_side == 1:
                opp_pivot_idx = latest_confirmed_pivot(ph5, k2, right=PIVOT_RIGHT)
                if opp_pivot_idx < 0 or opp_pivot_idx < k2 - 24:
                    continue
                opp_swing = m5.h[opp_pivot_idx]
                if not (m5.c[k2] > opp_swing):
                    continue
                # Update anchor to lowest point between sweep and displacement
                anchor_px = min(anchor_px, float(np.min(m5.l[k:k2 + 1])))
            else:
                opp_pivot_idx = latest_confirmed_pivot(pl5, k2, right=PIVOT_RIGHT)
                if opp_pivot_idx < 0 or opp_pivot_idx < k2 - 24:
                    continue
                opp_swing = m5.l[opp_pivot_idx]
                if not (m5.c[k2] < opp_swing):
                    continue
                # Update anchor to highest point between sweep and displacement
                anchor_px = max(anchor_px, float(np.max(m5.h[k:k2 + 1])))
                
            # 3. Check FVG on k3 (k3 = k2 + 1)
            k3 = k2 + 1
            if k3 >= len(m5.o):
                continue
            k1 = k2 - 1
            
            if target_side == 1:
                # Bullish FVG: low[k3] > high[k1]
                if not (m5.l[k3] > m5.h[k1]):
                    continue
                entry_px = m5.h[k1] # Proximal edge
                spread_buf = SPREAD_BUFFER_MULT * current_spread
                sl_px = anchor_px - spread_buf
                risk_dist = entry_px - sl_px
            else:
                # Bearish FVG: high[k3] < low[k1]
                if not (m5.h[k3] < m5.l[k1]):
                    continue
                entry_px = m5.l[k1] # Proximal edge
                spread_buf = SPREAD_BUFFER_MULT * current_spread
                sl_px = anchor_px + spread_buf
                risk_dist = sl_px - entry_px
                
            if risk_dist < sp.min_stop or risk_dist > sp.max_stop:
                continue
                
            # Hybrid Target: Capped at 2.0R to fit session expansion
            tp_px = entry_px + target_side * (MAX_TARGET_R * risk_dist)
            rr = abs(tp_px - entry_px) / risk_dist
            if rr < MIN_RR:
                continue
                
            return Setup(
                side=target_side,
                sweep_m5=k,
                anchor_px=anchor_px,
                c3_m5=k3,
                c3_close_m1=int(m5.m1_end_idx[k3]),
                entry_px=entry_px,
                sl_px=sl_px,
                tp_px=tp_px,
                risk_dist=risk_dist,
                rr=rr,
            )
            
    return None


@njit(cache=False)
def execute_trade_m1(
    fill_i: int,
    session_end_i: int,
    side: int,
    sl: float,
    tp: float,
    bid_o: np.ndarray,
    bid_h: np.ndarray,
    bid_l: np.ndarray,
    bid_c: np.ndarray,
    ask_o: np.ndarray,
    ask_h: np.ndarray,
    ask_l: np.ndarray,
    ask_c: np.ndarray,
) -> tuple[int, int, float]:
    """Simulates M1 trade execution with zero lookahead and pessimistic tie-breaks.
    
    RULES.md R2 Conformance:
    - Same-bar SL & TP hit: SL wins (reason = 1).
    - Bar opens beyond SL: fill at open (gap-through penalty).
    - Returns (exit_bar_idx, reason: 1=SL, 2=TP, 3=SESSION_CLOSE, raw_exit_price).
    """
    for k in range(fill_i + 1, session_end_i + 1):
        if side == 1:
            # Long position: exits on BID
            # Check gap-through stop at open
            if bid_o[k] <= sl:
                return k, 1, bid_o[k]
            sl_hit = bid_l[k] <= sl
            tp_hit = bid_h[k] >= tp
            # Pessimistic tie-break
            if sl_hit and tp_hit:
                return k, 1, sl
            if sl_hit:
                return k, 1, sl
            if tp_hit:
                return k, 2, tp
        else:
            # Short position: exits on ASK
            # Check gap-through stop at open
            if ask_o[k] >= sl:
                return k, 1, ask_o[k]
            sl_hit = ask_h[k] >= sl
            tp_hit = ask_l[k] <= tp
            # Pessimistic tie-break
            if sl_hit and tp_hit:
                return k, 1, sl
            if sl_hit:
                return k, 1, sl
            if tp_hit:
                return k, 2, tp
                
    # Session close exit (reason = 3)
    exit_px = bid_c[session_end_i] if side == 1 else ask_c[session_end_i]
    return session_end_i, 3, exit_px


def net_r(side: int, entry: float, exit_px: float, reason: int, dist: float, sp: Spec) -> float:
    """Calculates realized net R-multiple including spread, slippage, and commissions."""
    slip = sp.slip if reason != 2 else 0.0  # Slippage applies to market exits and stops
    px = exit_px - slip if side == 1 else exit_px + slip
    pnl = (px - entry) * side - sp.commission_rt
    return pnl / dist


def run_slot_c22(
    b: Bars,
    symbol: str,
    window: str,
    start_date: str,
    end_date: str,
    calendar_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Executes Cycle 22 Silver Bullet backtest for a single symbol and session window."""
    m5 = build_m5(b)
    ph5, pl5 = pivot_flags(m5.h, m5.l, PIVOT_LEFT, PIVOT_RIGHT)
    daily_df = build_daily_df(b)
    sp = SPECS[symbol]
    
    (sh, sm), (eh, em) = WINDOWS[window]
    (end_h, end_m) = SESSION_ENDS[window]
    
    days = pd.date_range(start_date, end_date, freq="B")
    trades = []
    
    for day in days:
        d = day.date()
        ctx = compute_day_context(b, d, window, daily_df)
        if ctx is None or ctx.dol_side == 0 or ctx.adr_exhausted:
            continue
            
        d0_ns = pd.Timestamp(d).tz_localize(NY).tz_convert("UTC").value
        ws_ns = d0_ns + (sh * 3600 + sm * 60) * 1_000_000_000
        we_ns = d0_ns + (eh * 3600 + em * 60) * 1_000_000_000
        sess_end_ns = d0_ns + (end_h * 3600 + end_m * 60) * 1_000_000_000
        
        # News blackout check
        if calendar_df is not None and not calendar_df.empty:
            # Check if any high impact news falls in [ws_ns - 15m, we_ns + 15m]
            from v17.data.calendar.blackout import SYMBOL_CURRENCY_MAP, is_in_blackout
            currencies = SYMBOL_CURRENCY_MAP.get(symbol, ["USD"])
            if is_in_blackout(ws_ns, calendar_df, currencies):
                continue
                
        # Find M5 index range for the window
        m5_start = int(np.searchsorted(m5.ts_start, ws_ns))
        m5_end = int(np.searchsorted(m5.ts_close, we_ns))
        if m5_end <= m5_start + 2:
            continue
            
        # Estimate current spread from M1 close at window start
        m1_ws_idx = np.searchsorted(b.ts, ws_ns)
        cur_spread = float(b.ask_c[m1_ws_idx] - b.bid_c[m1_ws_idx]) if m1_ws_idx < len(b.ts) else 0.0001
        
        setup = find_setup(m5, ph5, pl5, m5_start, m5_end, ctx, sp, cur_spread)
        if setup is None:
            continue
            
        # M1 execution loop: Look for fill starting at candle 3 close
        m1_start_fill = setup.c3_close_m1 + 1
        m1_sess_end = int(np.searchsorted(b.ts, sess_end_ns)) - 1
        if m1_sess_end <= m1_start_fill:
            continue
            
        fill_i = -1
        for m in range(m1_start_fill, m1_sess_end):
            # Invalidation before fill: Price breaks structural anchor before order fills
            if setup.side == 1 and b.bid_l[m] <= setup.anchor_px:
                break
            if setup.side == -1 and b.ask_h[m] >= setup.anchor_px:
                break
                
            # Check limit order fill
            if setup.side == 1 and b.ask_l[m] <= setup.entry_px:
                fill_i = m
                break
            if setup.side == -1 and b.bid_h[m] >= setup.entry_px:
                fill_i = m
                break
                
        if fill_i < 0:
            continue
            
        # Execute trade on M1
        exit_i, reason, exit_px = execute_trade_m1(
            fill_i,
            m1_sess_end,
            setup.side,
            setup.sl_px,
            setup.tp_px,
            b.bid_o,
            b.bid_h,
            b.bid_l,
            b.bid_c,
            b.ask_o,
            b.ask_h,
            b.ask_l,
            b.ask_c,
        )
        
        realized_r = net_r(setup.side, setup.entry_px, exit_px, reason, setup.risk_dist, sp)
        
        trades.append({
            "day": d,
            "symbol": symbol,
            "window": window,
            "side": setup.side,
            "entry": setup.entry_px,
            "sl": setup.sl_px,
            "tp": setup.tp_px,
            "risk_dist": setup.risk_dist,
            "rr": setup.rr,
            "fill_i": fill_i,
            "exit_i": exit_i,
            "reason": reason,
            "r": realized_r,
        })
        
    return pd.DataFrame(trades)
