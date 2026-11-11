"""ORB engine runner — per-fold OOS batch execution.

Design contract (anti-regression on handoff line 71):
  Per-symbol preprocessing (ATR_14, session VWAP, OR window ns per day,
  mid-price bars, numpy arrays) runs ONCE in `run_engine_oos_batch`. The
  fold loop slices the cached arrays by index — never calls `pd.concat`.

Trade lifecycle per day inside the OOS window:
  1. Compute OR high/low across the OR window (09:30-10:00 NY).
  2. Run `ORBFSM.on_bar` across session-window bars until a signal or EXIT.
  3. On signal: compute sl = stop_price ± SL_ATR_MULT * atr14[armed_idx].
     Compute initial tp = stop_price ∓ TARGET_R * (sl - stop_price).
  4. Call `simulate_fill_stop(mid_bars, armed_idx, side, stop_price, sl, tp,
                              session_end_ns - armed_ns, slippage_pts)`.
  5. If filled: walk bars entry..session_end; on each bar, if session VWAP is
     farther from entry than 0.5R, update tp to VWAP and continue; else keep
     tp at 0.5R. Exit on SL/TP/TIME.
  6. Record trade row.
  7. One signal/day/instrument (FSM already enforces via day_signal_emitted).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import pytz

from v17.backtest.fills import simulate_fill_stop
from v17.backtest.walkforward import Fold
from v17.setups.orb_constants import (
    ATR_PERIOD_M1,
    COST_SLIPPAGE_PTS,
    MAX_TRADES_PER_DAY_PER_INSTRUMENT,
    OR_WINDOW_NY,
    SESSION_WINDOW_NY,
    SL_ATR_MULT,
    TARGET_R,
)
from v17.setups.orb_engines import ORBEngineConfig
from v17.setups.orb_fsm import ORBFSM
from v17.structure.vwap import compute_session_vwap


_NS_PER_MIN = 60_000_000_000
_NS_PER_DAY = 86_400_000_000_000
_NY = pytz.timezone("America/New_York")


@dataclass
class TradeLog:
    engine_id: str
    fold_id: int
    trades: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------- helpers

def _window_ns(ny_date, window_ny: tuple[str, str]) -> tuple[int, int]:
    sh, sm = int(window_ny[0][:2]), int(window_ny[0][3:])
    eh, em = int(window_ny[1][:2]), int(window_ny[1][3:])
    start_naive = datetime(ny_date.year, ny_date.month, ny_date.day, sh, sm)
    end_naive = datetime(ny_date.year, ny_date.month, ny_date.day, eh, em)
    start_utc = _NY.localize(start_naive).astimezone(timezone.utc)
    end_utc = _NY.localize(end_naive).astimezone(timezone.utc)
    return pd.Timestamp(start_utc).value, pd.Timestamp(end_utc).value


def _to_mid_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Build mid-price bar DataFrame from bid/ask paired bars."""
    mid_o = (bars["bid_o"].to_numpy() + bars["ask_o"].to_numpy()) * 0.5
    mid_h = (bars["bid_h"].to_numpy() + bars["ask_h"].to_numpy()) * 0.5
    mid_l = (bars["bid_l"].to_numpy() + bars["ask_l"].to_numpy()) * 0.5
    mid_c = (bars["bid_c"].to_numpy() + bars["ask_c"].to_numpy()) * 0.5
    vol = (bars.get("bid_volume", pd.Series(1.0, index=bars.index)).to_numpy()
           + bars.get("ask_volume", pd.Series(1.0, index=bars.index)).to_numpy())
    return pd.DataFrame({
        "ts_ns": bars["ts_utc"].to_numpy(dtype=np.int64),
        "open": mid_o,
        "high": mid_h,
        "low": mid_l,
        "close": mid_c,
        "volume": vol,
    })


def _rolling_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    tr = np.maximum.reduce([
        high - low,
        np.abs(high - np.concatenate(([close[0]], close[:-1]))),
        np.abs(low - np.concatenate(([close[0]], close[:-1]))),
    ])
    # Simple moving average TR (not Wilder's — simpler + stable for our 0.5x mult).
    atr = np.full_like(tr, np.nan, dtype=float)
    if len(tr) < period:
        return atr
    cumsum = np.cumsum(tr)
    atr[period - 1] = cumsum[period - 1] / period
    for i in range(period, len(tr)):
        atr[i] = (cumsum[i] - cumsum[i - period]) / period
    return atr


def _ny_date_from_ns(ns: int):
    return pd.Timestamp(ns, tz="UTC").astimezone(_NY).date()


# ---------------------------------------------------------------- public API

def run_engine_oos_batch(
    config: ORBEngineConfig,
    bars: pd.DataFrame,
    calendar: pd.DataFrame,  # unused this cycle (news policy D deferred)
    folds: list[Fold],
) -> list[TradeLog]:
    """Run the ORB engine over N folds.

    Per-symbol preprocessing runs ONCE here; each fold slices by index.
    """
    if bars.empty:
        return [TradeLog(engine_id=config.engine_id, fold_id=f.fold_id) for f in folds]

    # 1) Mid-bar view + sort by ts_ns ascending.
    mid = _to_mid_bars(bars).sort_values("ts_ns").reset_index(drop=True)
    ts_ns = mid["ts_ns"].to_numpy()

    # 2) ATR_14 across the entire series — fold-independent.
    atr = _rolling_atr(
        mid["high"].to_numpy(),
        mid["low"].to_numpy(),
        mid["close"].to_numpy(),
        ATR_PERIOD_M1,
    )

    # 3) Precompute per-day OR/session window ns boundaries + day boundaries.
    #    Key by NY date (not UTC) so sessions align to NY calendar.
    #    Vectorized: pd.to_datetime on int64 ns -> tz_convert NY -> .date.
    _dt_utc = pd.to_datetime(ts_ns, unit="ns", utc=True)
    _dt_ny = _dt_utc.tz_convert("America/New_York")
    day_keys = _dt_ny.date  # numpy array of datetime.date
    day_keys = np.asarray(day_keys)
    unique_days, first_idx = np.unique(day_keys, return_index=True)
    # Sort by first_idx so we iterate chronologically.
    order = np.argsort(first_idx)
    unique_days = unique_days[order]
    first_idx = first_idx[order]

    day_info: list[dict] = []
    for i, d in enumerate(unique_days):
        or_start, or_end = _window_ns(d, OR_WINDOW_NY)
        sess_start, sess_end = _window_ns(d, SESSION_WINDOW_NY)
        day_info.append({
            "date": d,
            "or_start": or_start,
            "or_end": or_end,
            "sess_start": sess_start,
            "sess_end": sess_end,
        })

    # 4) Precompute session VWAP per day — vectorized across all days at once.
    #    Build sess_start/sess_end per bar via day_info lookup, then compute
    #    cumulative weighted TP grouped by (date, in-session) key.
    sess_start_arr = np.array([info["sess_start"] for info in day_info], dtype=np.int64)
    sess_end_arr = np.array([info["sess_end"] for info in day_info], dtype=np.int64)
    # Map each bar to its day index via pandas Categorical over day_keys.
    day_to_idx = {d: i for i, d in enumerate(unique_days)}
    bar_day_idx = np.array([day_to_idx[d] for d in day_keys], dtype=np.int64)
    bar_sess_start = sess_start_arr[bar_day_idx]
    bar_sess_end = sess_end_arr[bar_day_idx]
    in_session = (ts_ns >= bar_sess_start) & (ts_ns <= bar_sess_end)

    tp = (mid["high"].to_numpy() + mid["low"].to_numpy() + mid["close"].to_numpy()) / 3.0
    vol_arr = mid["volume"].to_numpy(dtype=float)
    vol_safe = np.where(vol_arr <= 0, 1.0, vol_arr)
    # Per-day cumulative VWAP: reset cumulation on day boundaries.
    # Trick: compute cumsum of (tp*vol) and cumsum of vol, subtract per-day baseline.
    w = tp * vol_safe
    cw = np.cumsum(np.where(in_session, w, 0.0))
    cv = np.cumsum(np.where(in_session, vol_safe, 0.0))
    # Baseline = cumsum value at first index of each day's in-session region.
    # For each day, find the first bar where in_session is True.
    vwap_arr = np.full(len(mid), np.nan, dtype=float)
    # Group by bar_day_idx and compute cumulative vwap per group manually via np.diff.
    # Use pandas groupby cumsum for simplicity — single pass, vectorized.
    w_in = np.where(in_session, w, 0.0)
    v_in = np.where(in_session, vol_safe, 0.0)
    df_tmp = pd.DataFrame({"g": bar_day_idx, "w": w_in, "v": v_in, "in_sess": in_session})
    cw_g = df_tmp.groupby("g")["w"].cumsum().to_numpy()
    cv_g = df_tmp.groupby("g")["v"].cumsum().to_numpy()
    cv_g_safe = np.where(cv_g <= 0, 1.0, cv_g)
    vwap_arr_computed = cw_g / cv_g_safe
    vwap_arr = np.where(in_session, vwap_arr_computed, np.nan)
    vwap = pd.Series(vwap_arr, index=mid.index)

    slippage = COST_SLIPPAGE_PTS[config.symbol]

    # Precompute per-day index ranges so fold loop is O(days_in_fold), not O(days^2).
    day_first = {d: int(first_idx[i]) for i, d in enumerate(unique_days)}
    # Last index per day = first index of the NEXT day - 1 (or len-1 for the last day).
    sorted_first = sorted(day_first.items(), key=lambda kv: kv[1])
    day_last: dict = {}
    for i, (d, f_i) in enumerate(sorted_first):
        nxt = sorted_first[i + 1][1] if i + 1 < len(sorted_first) else len(mid)
        day_last[d] = nxt - 1

    logs: list[TradeLog] = []
    for fold in folds:
        tl = TradeLog(engine_id=config.engine_id, fold_id=fold.fold_id)
        fold_mask = (ts_ns >= fold.oos_start) & (ts_ns < fold.oos_end)
        if not fold_mask.any():
            logs.append(tl)
            continue
        fold_idx = np.where(fold_mask)[0]
        fold_day_keys_arr = day_keys[fold_idx]
        for d in np.unique(fold_day_keys_arr):
            info = day_info[day_to_idx[d]]
            d_first = day_first[d]
            d_last = day_last[d]
            day_idx = np.arange(d_first, d_last + 1)
            day_slice = mid.iloc[day_idx[0]: day_idx[-1] + 1].reset_index(drop=True)
            day_slice_atr = atr[day_idx[0]: day_idx[-1] + 1]
            day_slice_vwap = vwap.iloc[day_idx[0]: day_idx[-1] + 1].to_numpy()

            trade = _run_one_day(
                config=config,
                mid_day=day_slice,
                atr_day=day_slice_atr,
                vwap_day=day_slice_vwap,
                or_start=info["or_start"],
                or_end=info["or_end"],
                sess_end=info["sess_end"],
                slippage_pts=slippage,
            )
            if trade is not None:
                trade["engine_id"] = config.engine_id
                trade["fold_id"] = fold.fold_id
                trade["symbol"] = config.symbol
                tl.trades.append(trade)
                # FSM enforces 1 signal/day; no extra cap needed.
        logs.append(tl)
    return logs


def run_engine_oos(
    config: ORBEngineConfig,
    bars: pd.DataFrame,
    calendar: pd.DataFrame,
    fold: Fold,
) -> TradeLog:
    return run_engine_oos_batch(config, bars, calendar, [fold])[0]


# ------------------------------------------------------------- one-day inner

def _run_one_day(
    config: ORBEngineConfig,
    mid_day: pd.DataFrame,
    atr_day: np.ndarray,
    vwap_day: np.ndarray,
    or_start: int,
    or_end: int,
    sess_end: int,
    slippage_pts: float,
) -> dict | None:
    fsm = ORBFSM(or_start, or_end, sess_end)
    signal = None
    for i, row in mid_day.iterrows():
        sig = fsm.on_bar(row, int(i))
        if sig is not None:
            signal = sig
            break
    if signal is None:
        return None

    atr14 = float(atr_day[signal.armed_bar_idx])
    if not np.isfinite(atr14) or atr14 <= 0:
        return None

    if signal.side == "short":
        sl = signal.stop_price + SL_ATR_MULT * atr14
        r_dist = sl - signal.stop_price
        tp_initial = signal.stop_price - TARGET_R * r_dist
    else:
        sl = signal.stop_price - SL_ATR_MULT * atr14
        r_dist = signal.stop_price - sl
        tp_initial = signal.stop_price + TARGET_R * r_dist

    time_cap_ns = sess_end - signal.armed_ns
    fill = simulate_fill_stop(
        bars=mid_day,
        armed_idx=signal.armed_bar_idx,
        side=signal.side,
        stop_price=signal.stop_price,
        sl=sl,
        tp=tp_initial,
        time_cap_ns=time_cap_ns,
        slippage_pts=slippage_pts,
    )
    if fill is None:
        return None

    # VWAP trail logic: from entry_idx forward, raise/lower tp to VWAP when
    # VWAP sits farther from entry than 0.5R.
    entry_idx = fill["entry_idx"]
    entry_price = fill["entry_price"]
    final_fill = fill  # default if no VWAP update triggers an earlier exit
    current_tp = tp_initial

    highs = mid_day["high"].to_numpy()
    lows = mid_day["low"].to_numpy()
    ts_ns_day = mid_day["ts_ns"].to_numpy()

    for j in range(entry_idx, len(mid_day)):
        if ts_ns_day[j] > sess_end:
            final_fill = {
                "entry_price": entry_price,
                "entry_idx": entry_idx,
                "exit_price": mid_day["close"].iloc[j],
                "exit_idx": j,
                "exit_reason": "TIME",
            }
            break
        vw = vwap_day[j]
        if np.isfinite(vw):
            if signal.side == "short":
                vwap_dist = entry_price - vw  # positive when VWAP below entry
                if vwap_dist > TARGET_R * r_dist:
                    current_tp = min(current_tp, vw)
                if highs[j] >= sl:
                    final_fill = {
                        "entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": sl, "exit_idx": j, "exit_reason": "SL",
                    }
                    break
                if lows[j] <= current_tp:
                    final_fill = {
                        "entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": current_tp, "exit_idx": j, "exit_reason": "TP",
                    }
                    break
            else:  # long
                vwap_dist = vw - entry_price
                if vwap_dist > TARGET_R * r_dist:
                    current_tp = max(current_tp, vw)
                if lows[j] <= sl:
                    final_fill = {
                        "entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": sl, "exit_idx": j, "exit_reason": "SL",
                    }
                    break
                if highs[j] >= current_tp:
                    final_fill = {
                        "entry_price": entry_price, "entry_idx": entry_idx,
                        "exit_price": current_tp, "exit_idx": j, "exit_reason": "TP",
                    }
                    break
    else:
        # Ran out of bars within day — close at last close.
        final_fill = {
            "entry_price": entry_price,
            "entry_idx": entry_idx,
            "exit_price": mid_day["close"].iloc[-1],
            "exit_idx": len(mid_day) - 1,
            "exit_reason": "TIME",
        }

    # pnl in R-multiples (direction aware).
    if signal.side == "short":
        pnl_abs = entry_price - final_fill["exit_price"]
    else:
        pnl_abs = final_fill["exit_price"] - entry_price
    pnl_r = pnl_abs / r_dist if r_dist > 0 else 0.0

    return {
        "ts_entry_ns": int(ts_ns_day[entry_idx]),
        "ts_exit_ns": int(ts_ns_day[final_fill["exit_idx"]]),
        "side": signal.side,
        "entry_price": float(entry_price),
        "exit_price": float(final_fill["exit_price"]),
        "sl": float(sl),
        "tp_initial": float(tp_initial),
        "tp_final": float(current_tp) if "current_tp" in dir() else float(tp_initial),
        "exit_reason": final_fill["exit_reason"],
        "r_dist": float(r_dist),
        "pnl_r": float(pnl_r),
        "pnl_cash": 0.0,  # populated at portfolio layer with equity + sizing
    }
