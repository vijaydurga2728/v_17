"""Cycle 9 — PDH/PDL liquidity sweep reversal, deterministic rule implementation.

Authoritative spec (read in this order; later wins on conflict):
  1. docs/superpowers/specs/2026-11-16-cycle9-smc-liquidity-prereg.md  §1-15
  2. docs/superpowers/specs/2026-11-16-cycle9-adr-001-phase2-corrections.md
  3. docs/superpowers/specs/2026-11-17-cycle9-adr-002-mcpt-null-and-stopping.md

Implementation interpretations not spelled out verbatim in the spec are tagged
``[IMPL-n]`` and listed in docs/superpowers/plans/c9_phase3_implementation_notes.md.

Data model: a ``Sessions`` object holds the tradable M15 bars of every full RTH
day, concatenated in time order, with ``offsets`` marking session boundaries.
Everything downstream (levels, ATR, simulation, MCPT null) works on that shape.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

try:  # numba is optional; the pure-Python path gives identical results.
    from numba import njit as _njit

    def _jit(f: Callable[..., Any]) -> Callable[..., Any]:
        return _njit(cache=False)(f)

    HAVE_NUMBA: Final[bool] = True
except ImportError:  # pragma: no cover - exercised only without numba

    def _jit(f: Callable[..., Any]) -> Callable[..., Any]:
        return f

    HAVE_NUMBA = False  # type: ignore[misc]

# ---------------------------------------------------------------- constants
SYMBOL: Final[str] = "USATECHIDXUSD"
NY_TZ: Final[str] = "America/New_York"
RTH_OPEN_MIN: Final[int] = 9 * 60 + 30   # 09:30 ET
BIN_MIN: Final[int] = 15
N_TRADABLE_BINS: Final[int] = 25          # [09:30, 15:45); ADR 001 B
TRADABLE_END_MIN: Final[int] = RTH_OPEN_MIN + N_TRADABLE_BINS * BIN_MIN  # 15:45
MIN_M1_PER_BIN: Final[int] = 5            # pre-reg §6 incomplete-bar rule
ATR_N: Final[int] = 14
FULL_DAY: Final[pd.Timedelta] = pd.Timedelta(hours=6, minutes=30)

DEV_START: Final[str] = "2015-01-01"
DEV_END: Final[str] = "2022-12-31"
HOLDOUT_START: Final[str] = "2023-01-01"
HOLDOUT_END: Final[str] = "2026-11-16"

SWEEP_BUFFERS: Final[tuple[float, ...]] = (0.00, 0.05, 0.10)
DIRECTIONS: Final[tuple[str, ...]] = ("long_only", "short_only")
N_CONFS: Final[tuple[int, ...]] = (1, 2)

# exit reason codes
STOP_GAP: Final[int] = 1
TARGET_GAP: Final[int] = 2
STOP: Final[int] = 3
TARGET: Final[int] = 4
EOD: Final[int] = 5
EXIT_REASONS: Final[dict[int, str]] = {
    STOP_GAP: "stop_gap", TARGET_GAP: "target_gap", STOP: "stop", TARGET: "target", EOD: "eod",
}

PRICE_FIELDS: Final[tuple[str, ...]] = (
    "bid_o", "bid_h", "bid_l", "bid_c",
    "ask_o", "ask_h", "ask_l", "ask_c",
    "mid_o", "mid_h", "mid_l", "mid_c",
)


@dataclass(frozen=True)
class Slot:
    sweep_buffer: float
    direction: str  # "long_only" | "short_only"
    n_conf: int

    @property
    def slot_id(self) -> str:
        return f"buf{self.sweep_buffer:.2f}_{self.direction}_n{self.n_conf}"


def all_slots() -> list[Slot]:
    """The 12 locked slots in the deterministic order used for seeds (ADR 001 A.3)."""
    keys = sorted((b, d, n) for b in SWEEP_BUFFERS for d in DIRECTIONS for n in N_CONFS)
    return [Slot(b, d, n) for b, d, n in keys]


# ----------------------------------------------------------------- calendar
def full_rth_days(start: str, end: str) -> np.ndarray:
    """NY dates (datetime64[D]) of full 09:30-16:00 XNYS sessions; half-days excluded.

    ADR 001 G: pandas_market_calendars XNYS, no fallback.
    """
    import pandas_market_calendars as pmc  # type: ignore[import-untyped]

    sched = pmc.get_calendar("XNYS").schedule(start_date=start, end_date=end)
    full = (sched["market_close"] - sched["market_open"]) == FULL_DAY
    return np.asarray(sched.index[full].to_numpy(dtype="datetime64[D]"))


# -------------------------------------------------------------- M15 builder
def build_m15(m1: pd.DataFrame, full_days: np.ndarray) -> pd.DataFrame:
    """Session-aligned M15 bars from paired M1 (pre-reg §6, ADR 001 B).

    Keeps only M1 bars inside [09:30, 15:45) ET on full days; drops bins with
    fewer than MIN_M1_PER_BIN M1 bars. The [15:45, 16:00) bin is never built.
    """
    if m1.empty:
        return pd.DataFrame()
    m1 = m1.sort_values("ts_utc", kind="mergesort")
    local = (
        pd.to_datetime(m1["ts_utc"].to_numpy(dtype=np.int64), unit="ns", utc=True)
        .tz_convert(NY_TZ).tz_localize(None).to_numpy()
    )
    date = local.astype("datetime64[D]")
    minute = ((local - date) // np.timedelta64(1, "m")).astype(np.int64)
    keep = (minute >= RTH_OPEN_MIN) & (minute < TRADABLE_END_MIN) & np.isin(date, full_days)
    df = m1.loc[keep, ["ts_utc", *[f for f in PRICE_FIELDS if not f.startswith("mid")]]].copy()
    df["date"] = date[keep]
    df["bin"] = (minute[keep] - RTH_OPEN_MIN) // BIN_MIN
    for col in ("bid_volume", "ask_volume"):
        df[col] = m1.loc[keep, col].to_numpy() if col in m1 else 0.0

    g = df.groupby(["date", "bin"], sort=True)
    out = pd.DataFrame({
        "bid_o": g["bid_o"].first(), "bid_h": g["bid_h"].max(),
        "bid_l": g["bid_l"].min(), "bid_c": g["bid_c"].last(),
        "ask_o": g["ask_o"].first(), "ask_h": g["ask_h"].max(),
        "ask_l": g["ask_l"].min(), "ask_c": g["ask_c"].last(),
        "bid_volume": g["bid_volume"].sum(), "ask_volume": g["ask_volume"].sum(),
        "n_m1_bars": g["ts_utc"].count(),
    }).reset_index()
    out = out[out["n_m1_bars"] >= MIN_M1_PER_BIN].reset_index(drop=True)
    for s in ("o", "h", "l", "c"):
        out[f"mid_{s}"] = (out[f"bid_{s}"] + out[f"ask_{s}"]) * 0.5
    start_local = (
        out["date"].to_numpy(dtype="datetime64[m]")
        + (RTH_OPEN_MIN + out["bin"].to_numpy() * BIN_MIN).astype("timedelta64[m]")
    )
    out["ts_utc"] = (
        pd.DatetimeIndex(start_local).tz_localize(NY_TZ).tz_convert(None)
        .to_numpy(dtype="datetime64[ns]").view(np.int64)
    )
    return out


# ----------------------------------------------------------------- sessions
@dataclass
class Sessions:
    dates: np.ndarray        # (K,) datetime64[D] NY date of each session
    offsets: np.ndarray      # (K+1,) int64; session s = bars offsets[s]:offsets[s+1]
    bins: np.ndarray         # (N,) int64 bin number 0..24
    prices: dict[str, np.ndarray]  # PRICE_FIELDS -> (N,) float64
    prev_ok: np.ndarray      # (K,) bool: session s-1 is the calendar-previous full day

    @property
    def n_sessions(self) -> int:
        return len(self.dates)

    def __getitem__(self, field: str) -> np.ndarray:
        return self.prices[field]


def sessions_from_m15(m15: pd.DataFrame, full_days: np.ndarray) -> Sessions:
    """Group M15 bars into sessions. ``prev_ok[s]`` implements pre-reg §7:
    PDH/PDL for D come from the most-recent full RTH day strictly before D; if
    that day has no data, D gets no levels ([IMPL-1])."""
    m15 = m15.sort_values(["date", "bin"], kind="mergesort").reset_index(drop=True)
    d = m15["date"].to_numpy(dtype="datetime64[D]")
    starts = np.flatnonzero(np.r_[True, d[1:] != d[:-1]]) if len(d) else np.array([], np.int64)
    offsets = np.r_[starts, len(d)].astype(np.int64)
    dates = d[starts]
    if not np.isin(dates, full_days).all():
        raise ValueError("session date not in full-day calendar")
    cal_pos = np.searchsorted(full_days, dates)
    prev_ok = np.zeros(len(dates), dtype=bool)
    if len(dates) > 1:
        prev_ok[1:] = cal_pos[1:] == cal_pos[:-1] + 1
    prices = {f: m15[f].to_numpy(dtype=np.float64).copy() for f in PRICE_FIELDS}
    return Sessions(dates, offsets, m15["bin"].to_numpy(dtype=np.int64), prices, prev_ok)


def levels(sess: Sessions) -> tuple[np.ndarray, np.ndarray]:
    """PDH/PDL per session (pre-reg §7) from the previous session's M15 mid_h/mid_l.

    NaN where the previous calendar full day is missing or for the first session.
    """
    k = sess.n_sessions
    pdh = np.full(k, np.nan)
    pdl = np.full(k, np.nan)
    if k < 2:
        return pdh, pdl
    starts = sess.offsets[:-1]
    day_h = np.maximum.reduceat(sess["mid_h"], starts)
    day_l = np.minimum.reduceat(sess["mid_l"], starts)
    pdh[1:] = np.where(sess.prev_ok[1:], day_h[:-1], np.nan)
    pdl[1:] = np.where(sess.prev_ok[1:], day_l[:-1], np.nan)
    return pdh, pdl


# ---------------------------------------------------------------------- ATR
@_jit
def _atr_prev_core(h: np.ndarray, lo: np.ndarray, c: np.ndarray, n: int) -> np.ndarray:
    m = len(c)
    out = np.full(m, np.nan)
    if m <= n + 1:
        return out
    tr = np.full(m, np.nan)
    for i in range(1, m):
        a = h[i] - lo[i]
        b = abs(h[i] - c[i - 1])
        d = abs(lo[i] - c[i - 1])
        tr[i] = max(a, b, d)
    atr = tr[1:n + 1].mean()  # ATR at bar n: mean of first n valid TRs [IMPL-2]
    # atr_prev[i] = ATR[i-1]  (ADR 001 E.3, causal)
    out[n + 1] = atr
    for i in range(n + 1, m - 1):
        atr = (atr * (n - 1) + tr[i]) / n
        out[i + 1] = atr
    return out


def atr_prev(sess: Sessions) -> np.ndarray:
    """Wilder ATR(14) on the concatenated M15 mid stream, shifted one bar (ADR 001 E)."""
    return np.asarray(_atr_prev_core(sess["mid_h"], sess["mid_l"], sess["mid_c"], ATR_N))


# --------------------------------------------------------------- simulation
@_jit
def _simulate_core(  # noqa: PLR0912, PLR0915 - flat loop kept numba-compilable
    direction: int, buf: float, n_conf: int, slip: float,
    offsets: np.ndarray, pdh: np.ndarray, pdl: np.ndarray, atrp: np.ndarray,
    entry_ok: np.ndarray,
    bid_o: np.ndarray, bid_h: np.ndarray, bid_l: np.ndarray, bid_c: np.ndarray,
    ask_o: np.ndarray, ask_h: np.ndarray, ask_l: np.ndarray, ask_c: np.ndarray,
    mid_h: np.ndarray, mid_l: np.ndarray, mid_c: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (int_out[n,6], float_out[n,6], n_trades) arrays.

    int_out cols:   session, sweep_bar, confirm_bar, entry_bar, exit_bar, reason
    float_out cols: entry_px, stop, target, exit_px, r, rr_at_entry
    """
    k_sess = len(offsets) - 1
    iout = np.zeros((k_sess, 6), dtype=np.int64)
    fout = np.zeros((k_sess, 6), dtype=np.float64)
    nt = 0
    for s in range(k_sess):
        lvl_h = pdh[s]
        lvl_l = pdl[s]
        if not (np.isfinite(lvl_h) and np.isfinite(lvl_l)) or not entry_ok[s]:
            continue
        a = offsets[s]
        b = offsets[s + 1]
        # ---- sweep scan + confirmation (pre-reg §10.1-10.2, ADR 001 C, F)
        i = a
        pending = -1
        sweep = -1
        conf = -1
        while i < b:
            if pending >= 0:
                ok = mid_c[i] > mid_h[pending] if direction == 1 else mid_c[i] < mid_l[pending]
                if ok:
                    sweep = pending
                    conf = i
                    break
                if i >= pending + n_conf:
                    # window expired: resume at k + N_conf + 1; bars inside the expired
                    # window are never re-scanned as candidates [IMPL-3, decided 2026-11-17]
                    i = pending + n_conf + 1
                    pending = -1
                    continue
                i += 1
                continue
            if direction == 1:
                cand = mid_l[i] < lvl_l and mid_c[i] > lvl_l
            else:
                cand = mid_h[i] > lvl_h and mid_c[i] < lvl_h
            if cand and np.isfinite(atrp[i]):  # muted until ATR defined (ADR 001 E.5)
                pending = i
            i += 1
        if conf < 0 or conf + 1 >= b:
            continue  # no confirmation, or no bar left to enter (pre-reg §10.3)
        e = conf + 1
        # ---- entry, stop, target (pre-reg §10.3-10.5; slippage ADR 001 D)
        if direction == 1:
            entry = ask_o[e] + slip
            stop = mid_l[sweep] - buf * atrp[sweep]
            target = lvl_h
        else:
            entry = bid_o[e] - slip
            stop = mid_h[sweep] + buf * atrp[sweep]
            target = lvl_l
        stop_dist = abs(entry - stop)
        if not stop_dist > 0.0:
            continue  # degenerate: R undefined [IMPL-5]
        rr = (target - entry) / stop_dist if direction == 1 else (entry - target) / stop_dist
        # ---- fill priority from the entry bar onward (ADR 001 D) [IMPL-4]
        exit_px = np.nan
        reason = 0
        x = e
        for x in range(e, b):
            if direction == 1:
                if bid_o[x] <= stop:
                    exit_px = bid_o[x] - slip
                    reason = 1
                elif bid_o[x] >= target:
                    exit_px = bid_o[x] - slip
                    reason = 2
                elif bid_l[x] <= stop:
                    exit_px = stop - slip
                    reason = 3
                elif bid_h[x] >= target:
                    exit_px = target - slip
                    reason = 4
                elif x == b - 1:
                    exit_px = bid_c[x] - slip
                    reason = 5
            elif ask_o[x] >= stop:
                exit_px = ask_o[x] + slip
                reason = 1
            elif ask_o[x] <= target:
                exit_px = ask_o[x] + slip
                reason = 2
            elif ask_h[x] >= stop:
                exit_px = stop + slip
                reason = 3
            elif ask_l[x] <= target:
                exit_px = target + slip
                reason = 4
            elif x == b - 1:
                exit_px = ask_c[x] + slip
                reason = 5
            if reason != 0:
                break
        r = (exit_px - entry) / stop_dist if direction == 1 else (entry - exit_px) / stop_dist
        iout[nt, 0] = s
        iout[nt, 1] = sweep
        iout[nt, 2] = conf
        iout[nt, 3] = e
        iout[nt, 4] = x
        iout[nt, 5] = reason
        fout[nt, 0] = entry
        fout[nt, 1] = stop
        fout[nt, 2] = target
        fout[nt, 3] = exit_px
        fout[nt, 4] = r
        fout[nt, 5] = rr
        nt += 1
    return iout[:nt], fout[:nt], np.array([nt])


def entry_eligible(sess: Sessions) -> np.ndarray:
    """[IMPL-8, approved 2026-11-17] A session is entry-eligible only if its
    final tradable bin [15:30, 15:45) (bin 24) exists, so the pre-registered EOD exit price
    (that bin's close) is always defined. Ineligible sessions still supply PDH/PDL to the next day.
    """
    if sess.n_sessions == 0:
        return np.zeros(0, dtype=np.bool_)
    return np.asarray(sess.bins[sess.offsets[1:] - 1] == N_TRADABLE_BINS - 1, dtype=np.bool_)


def simulate_raw(
    sess: Sessions, pdh: np.ndarray, pdl: np.ndarray, atrp: np.ndarray,
    slot: Slot, slippage_pts: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Fast path: returns (int_out, float_out) arrays. ``float_out[:, 4]`` is R."""
    p = sess.prices
    iout, fout, _ = _simulate_core(
        1 if slot.direction == "long_only" else -1, float(slot.sweep_buffer), int(slot.n_conf),
        float(slippage_pts), sess.offsets, pdh, pdl, atrp, entry_eligible(sess),
        p["bid_o"], p["bid_h"], p["bid_l"], p["bid_c"],
        p["ask_o"], p["ask_h"], p["ask_l"], p["ask_c"],
        p["mid_h"], p["mid_l"], p["mid_c"],
    )
    return iout, fout


def simulate(
    sess: Sessions, pdh: np.ndarray, pdl: np.ndarray, atrp: np.ndarray,
    slot: Slot, slippage_pts: float = 0.0,
) -> pd.DataFrame:
    """One slot over all sessions; one row per trade."""
    iout, fout = simulate_raw(sess, pdh, pdl, atrp, slot, slippage_pts)
    return pd.DataFrame({
        "date": sess.dates[iout[:, 0]] if len(iout) else np.array([], "datetime64[D]"),
        "side": "long" if slot.direction == "long_only" else "short",
        "sweep_bin": sess.bins[iout[:, 1]],
        "confirm_bin": sess.bins[iout[:, 2]],
        "entry_bin": sess.bins[iout[:, 3]],
        "exit_bin": sess.bins[iout[:, 4]],
        "entry_px": fout[:, 0], "stop": fout[:, 1], "target": fout[:, 2],
        "exit_px": fout[:, 3], "r": fout[:, 4], "rr_at_entry": fout[:, 5],
        "exit_reason": [EXIT_REASONS[int(c)] for c in iout[:, 5]],
    })
