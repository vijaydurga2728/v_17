"""Donchian Channel breakout runner (cycle 4, S2).

Entry rule: H1 close breaks the prior-ENTRY_CHANNEL_H1-bar extreme.
  close[t] > max(high[t-20..t-1])  -> long signal at t+1 open.
  close[t] < min(low [t-20..t-1])  -> short signal at t+1 open.

Entry execution: next bar open with adverse slippage.
Initial stop: opposite 10-H1 channel extreme at entry (long: min(low[entry-10..entry-1])).
Trailing stop: recomputed each subsequent bar (long: max of running min(low[j-10..j-1])).
Target: 2R fixed from entry (R = |entry_price - initial_stop|).
Exit: whichever comes first — trailing SL touched, TP touched, or end of data.

One trade open at a time per engine-instrument pair (no pyramid).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from v17.backtest.engine_runner import TradeLog, _to_mid_bars
from v17.backtest.walkforward import Fold
from v17.common.instrument_spec import pip_size
from v17.setups.donchian_constants import (
    COST_SLIPPAGE_PIPS_FX,
    COST_SLIPPAGE_PTS,
    ENTRY_CHANNEL_H1,
    TARGET_R,
    TRAIL_CHANNEL_H1,
)
from v17.setups.donchian_engines import DonchianEngineConfig


def _slippage_price(symbol: str) -> float:
    if symbol in COST_SLIPPAGE_PTS:
        return COST_SLIPPAGE_PTS[symbol]
    return COST_SLIPPAGE_PIPS_FX * pip_size(symbol)


def _rolling_extremes(
    high: np.ndarray, low: np.ndarray, window: int
) -> tuple[np.ndarray, np.ndarray]:
    """Return (rolling_max_high, rolling_min_low) over the prior `window` bars.

    Index i holds max/min over [i-window, i-1]. Entries before `window` are NaN.
    """
    n = len(high)
    max_h = np.full(n, np.nan)
    min_l = np.full(n, np.nan)
    for i in range(window, n):
        max_h[i] = high[i - window: i].max()
        min_l[i] = low[i - window: i].min()
    return max_h, min_l


def run_donchian_oos_batch(
    config: DonchianEngineConfig,
    bars_h1: pd.DataFrame,
    folds: list[Fold],
) -> list[TradeLog]:
    if bars_h1.empty:
        return [TradeLog(engine_id=config.engine_id, fold_id=f.fold_id) for f in folds]

    mid = _to_mid_bars(bars_h1).sort_values("ts_ns").reset_index(drop=True)
    ts_ns = mid["ts_ns"].to_numpy()
    high = mid["high"].to_numpy()
    low = mid["low"].to_numpy()
    close = mid["close"].to_numpy()
    open_ = mid["open"].to_numpy()

    entry_max, entry_min = _rolling_extremes(high, low, ENTRY_CHANNEL_H1)
    trail_max, trail_min = _rolling_extremes(high, low, TRAIL_CHANNEL_H1)

    slippage = _slippage_price(config.symbol)

    logs: list[TradeLog] = []
    for fold in folds:
        tl = TradeLog(engine_id=config.engine_id, fold_id=fold.fold_id)
        n = len(mid)
        i = max(ENTRY_CHANNEL_H1, TRAIL_CHANNEL_H1)
        while i < n - 1:
            if ts_ns[i] < fold.oos_start:
                i += 1
                continue
            if ts_ns[i] >= fold.oos_end:
                break
            # Breakout check on bar i close; entry on bar i+1 open.
            side = None
            if np.isfinite(entry_max[i]) and close[i] > entry_max[i]:
                side = "long"
            elif np.isfinite(entry_min[i]) and close[i] < entry_min[i]:
                side = "short"
            if side is None:
                i += 1
                continue

            entry_idx = i + 1
            if entry_idx >= n:
                break
            if side == "long":
                entry_price = open_[entry_idx] + slippage
                initial_stop = trail_min[entry_idx]
            else:
                entry_price = open_[entry_idx] - slippage
                initial_stop = trail_max[entry_idx]
            if not np.isfinite(initial_stop):
                i = entry_idx + 1
                continue
            r_dist = abs(entry_price - initial_stop)
            if r_dist <= 0:
                i = entry_idx + 1
                continue
            if side == "long":
                tp = entry_price + TARGET_R * r_dist
            else:
                tp = entry_price - TARGET_R * r_dist

            # Walk forward with trailing stop until TP/SL/fold-end.
            current_sl = initial_stop
            exit_idx = None
            exit_price = None
            exit_reason = None
            for j in range(entry_idx, n):
                if ts_ns[j] >= fold.oos_end:
                    exit_idx = j
                    exit_price = close[j]
                    exit_reason = "FOLD_END"
                    break
                # Update trailing stop AFTER entry bar (so entry bar uses initial).
                if j > entry_idx:
                    if side == "long" and np.isfinite(trail_min[j]):
                        current_sl = max(current_sl, trail_min[j])
                    elif side == "short" and np.isfinite(trail_max[j]):
                        current_sl = min(current_sl, trail_max[j])
                if side == "long":
                    if low[j] <= current_sl:
                        exit_idx = j
                        exit_price = current_sl
                        exit_reason = "SL"
                        break
                    if high[j] >= tp:
                        exit_idx = j
                        exit_price = tp
                        exit_reason = "TP"
                        break
                else:
                    if high[j] >= current_sl:
                        exit_idx = j
                        exit_price = current_sl
                        exit_reason = "SL"
                        break
                    if low[j] <= tp:
                        exit_idx = j
                        exit_price = tp
                        exit_reason = "TP"
                        break
            if exit_idx is None:
                exit_idx = n - 1
                exit_price = close[-1]
                exit_reason = "TIME"

            if side == "long":
                pnl_abs = float(exit_price) - entry_price
            else:
                pnl_abs = entry_price - float(exit_price)
            pnl_r = pnl_abs / r_dist if r_dist > 0 else 0.0

            trade = {
                "engine_id": config.engine_id,
                "fold_id": fold.fold_id,
                "symbol": config.symbol,
                "ts_entry_ns": int(ts_ns[entry_idx]),
                "ts_exit_ns": int(ts_ns[exit_idx]),
                "side": side,
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "sl": float(initial_stop),
                "tp": float(tp),
                "exit_reason": exit_reason,
                "r_dist": float(r_dist),
                "pnl_r": float(pnl_r),
                "pnl_cash": 0.0,
            }
            tl.trades.append(trade)
            i = exit_idx + 1
        logs.append(tl)
    return logs
