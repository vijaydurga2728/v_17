"""Overnight gap-fade engine runner (cycle 3).

Simpler than ORB — no OR window, no VWAP trail. One trade/day if gap
falls in [GAP_MIN_PCT, GAP_MAX_PCT]:
  gap > 0 -> short at 09:30 open; SL = open + |gap|; TP = open - 0.5*|gap|.
  gap < 0 -> long at 09:30 open;  SL = open - |gap|; TP = open + 0.5*|gap|.

Per-symbol preprocessing runs ONCE in `run_gap_oos_batch`; fold loop
slices by index (same anti-regression design as ORB engine runner).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytz

from v17.backtest.engine_runner import TradeLog, _to_mid_bars, _window_ns
from v17.backtest.fills import simulate_fill_market
from v17.backtest.walkforward import Fold
from v17.setups.gap_constants import (
    GAP_MAX_PCT,
    GAP_MIN_PCT,
    SESSION_CLOSE_NY,
    SESSION_OPEN_NY,
    TARGET_R,
)
from v17.setups.gap_engines import GapEngineConfig
from v17.setups.orb_constants import COST_SLIPPAGE_PTS


_NY = pytz.timezone("America/New_York")


def _session_window_ns(ny_date) -> tuple[int, int]:
    open_window = (f"{SESSION_OPEN_NY[0]:02d}:{SESSION_OPEN_NY[1]:02d}",
                   f"{SESSION_CLOSE_NY[0]:02d}:{SESSION_CLOSE_NY[1]:02d}")
    return _window_ns(ny_date, open_window)


def run_gap_oos_batch(
    config: GapEngineConfig,
    bars: pd.DataFrame,
    folds: list[Fold],
) -> list[TradeLog]:
    if bars.empty:
        return [TradeLog(engine_id=config.engine_id, fold_id=f.fold_id) for f in folds]

    mid = _to_mid_bars(bars).sort_values("ts_ns").reset_index(drop=True)
    ts_ns = mid["ts_ns"].to_numpy()

    # NY-date keying (vectorized).
    dt_utc = pd.to_datetime(ts_ns, unit="ns", utc=True)
    dt_ny = dt_utc.tz_convert("America/New_York")
    day_keys = np.asarray(dt_ny.date)
    unique_days, first_idx = np.unique(day_keys, return_index=True)
    order = np.argsort(first_idx)
    unique_days = unique_days[order]
    first_idx = first_idx[order]

    # Per-day session open/close ns and index ranges.
    sess_start_ns = np.zeros(len(unique_days), dtype=np.int64)
    sess_end_ns = np.zeros(len(unique_days), dtype=np.int64)
    for i, d in enumerate(unique_days):
        s, e = _session_window_ns(d)
        sess_start_ns[i] = s
        sess_end_ns[i] = e

    day_first = {d: int(first_idx[i]) for i, d in enumerate(unique_days)}
    sorted_first = sorted(day_first.items(), key=lambda kv: kv[1])
    day_last: dict = {}
    for i, (d, f_i) in enumerate(sorted_first):
        nxt = sorted_first[i + 1][1] if i + 1 < len(sorted_first) else len(mid)
        day_last[d] = nxt - 1

    # Precompute per-day: session open price and session close price.
    # session_open = mid.close of the first in-session bar; session_close = mid.close of last in-session bar.
    sess_open_price = np.full(len(unique_days), np.nan, dtype=float)
    sess_close_price = np.full(len(unique_days), np.nan, dtype=float)
    sess_open_idx = np.full(len(unique_days), -1, dtype=np.int64)
    mid_open_arr = mid["open"].to_numpy()
    mid_close_arr = mid["close"].to_numpy()

    for i, d in enumerate(unique_days):
        d_first = day_first[d]
        d_last = day_last[d]
        day_ts = ts_ns[d_first: d_last + 1]
        in_sess = (day_ts >= sess_start_ns[i]) & (day_ts <= sess_end_ns[i])
        if not in_sess.any():
            continue
        local_idx_in_sess = np.where(in_sess)[0]
        first_sess = d_first + local_idx_in_sess[0]
        last_sess = d_first + local_idx_in_sess[-1]
        sess_open_price[i] = mid_open_arr[first_sess]
        sess_close_price[i] = mid_close_arr[last_sess]
        sess_open_idx[i] = first_sess

    slippage = COST_SLIPPAGE_PTS[config.symbol]

    logs: list[TradeLog] = []
    for fold in folds:
        tl = TradeLog(engine_id=config.engine_id, fold_id=fold.fold_id)
        fold_mask = (ts_ns >= fold.oos_start) & (ts_ns < fold.oos_end)
        if not fold_mask.any():
            logs.append(tl)
            continue

        fold_days = np.unique(day_keys[np.where(fold_mask)[0]])
        # Walk days in order; need prior-day close for gap.
        day_to_idx = {d: i for i, d in enumerate(unique_days)}
        for d in fold_days:
            i = day_to_idx[d]
            if i == 0:
                continue  # no prior day
            prev_close = sess_close_price[i - 1]
            today_open = sess_open_price[i]
            if not (np.isfinite(prev_close) and np.isfinite(today_open) and prev_close > 0):
                continue
            gap = today_open - prev_close
            gap_pct = gap / prev_close
            if not (GAP_MIN_PCT <= abs(gap_pct) <= GAP_MAX_PCT):
                continue

            # Build day slice from session open onward.
            open_idx_global = int(sess_open_idx[i])
            d_last = day_last[d]
            day_slice_bars = mid.iloc[open_idx_global: d_last + 1].reset_index(drop=True)
            # time_cap_ns = session end - open ts
            open_ts = int(ts_ns[open_idx_global])
            cap = int(sess_end_ns[i] - open_ts)
            if cap <= 0:
                continue

            abs_gap = abs(gap)
            if gap > 0:
                side = "short"
                sl = today_open + abs_gap
                tp = today_open - TARGET_R * abs_gap
            else:
                side = "long"
                sl = today_open - abs_gap
                tp = today_open + TARGET_R * abs_gap

            fill = simulate_fill_market(
                bars=day_slice_bars,
                entry_idx=0,  # the session-open bar
                side=side,
                sl=sl,
                tp=tp,
                time_cap_ns=cap,
                slippage_pts=slippage,
            )

            entry_price = fill["entry_price"]
            exit_price = fill["exit_price"]
            r_dist = abs_gap
            if side == "short":
                pnl_abs = entry_price - exit_price
            else:
                pnl_abs = exit_price - entry_price
            pnl_r = pnl_abs / r_dist if r_dist > 0 else 0.0

            trade = {
                "engine_id": config.engine_id,
                "fold_id": fold.fold_id,
                "symbol": config.symbol,
                "ts_entry_ns": int(day_slice_bars["ts_ns"].iloc[0]),
                "ts_exit_ns": int(day_slice_bars["ts_ns"].iloc[fill["exit_idx"]]),
                "side": side,
                "gap_pct": float(gap_pct),
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "sl": float(sl),
                "tp": float(tp),
                "exit_reason": fill["exit_reason"],
                "r_dist": float(r_dist),
                "pnl_r": float(pnl_r),
                "pnl_cash": 0.0,
            }
            tl.trades.append(trade)
        logs.append(tl)
    return logs
