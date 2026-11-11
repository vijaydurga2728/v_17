"""Donchian channel breakout runner.

Cycle 4B (2026-11-11, [P-HACK-ACKNOWLEDGED]): Turtle rule 1 on D1.
See docs/superpowers/specs/2026-11-11-cycle4b-correction-prereg.md § 3 S2.

Entry rule (on D1 close):
  close[t] > max(high[t-20..t-1]) -> long  signal at t+1 open.
  close[t] < min(low [t-20..t-1]) -> short signal at t+1 open.

Entry execution: next D1 bar open with adverse slippage.
Initial stop: 2 × N where N = ATR_20(D1) at entry (Turtle '2N').
Trailing exit: opposite 10-D1 channel crossed (price touches).
  Long: exit if low <= min(low[j-10..j-1]).
  Short: exit if high >= max(high[j-10..j-1]).
No fixed take-profit. SL also honored (2N hard stop in addition to trailing channel).

One open position per engine-instrument at a time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.backtest.engine_runner import TradeLog, _to_mid_bars
from v17.backtest.walkforward import Fold
from v17.common.instrument_spec import pip_size
from v17.setups.donchian_constants import (
    ATR_PERIOD_D1,
    COST_SLIPPAGE_PIPS_FX,
    COST_SLIPPAGE_PTS,
    ENTRY_CHANNEL_D1,
    SL_ATR_MULT,
    TRAIL_CHANNEL_D1,
)
from v17.setups.donchian_engines import DonchianEngineConfig


def _slippage_price(symbol: str) -> float:
    if symbol in COST_SLIPPAGE_PTS:
        return COST_SLIPPAGE_PTS[symbol]
    return COST_SLIPPAGE_PIPS_FX * pip_size(symbol)


def _rolling_extremes(
    high: np.ndarray, low: np.ndarray, window: int
) -> tuple[np.ndarray, np.ndarray]:
    n = len(high)
    max_h = np.full(n, np.nan)
    min_l = np.full(n, np.nan)
    for i in range(window, n):
        max_h[i] = high[i - window: i].max()
        min_l[i] = low[i - window: i].min()
    return max_h, min_l


def _rolling_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    prev_close = np.concatenate(([close[0]], close[:-1]))
    tr = np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ])
    atr = np.full_like(tr, np.nan, dtype=float)
    if len(tr) < period:
        return atr
    cumsum = np.cumsum(tr)
    atr[period - 1] = cumsum[period - 1] / period
    for i in range(period, len(tr)):
        atr[i] = (cumsum[i] - cumsum[i - period]) / period
    return atr


def run_donchian_oos_batch(
    config: DonchianEngineConfig,
    bars_d1: pd.DataFrame,
    folds: list[Fold],
) -> list[TradeLog]:
    if bars_d1.empty:
        return [TradeLog(engine_id=config.engine_id, fold_id=f.fold_id) for f in folds]

    mid = _to_mid_bars(bars_d1).sort_values("ts_ns").reset_index(drop=True)
    ts_ns = mid["ts_ns"].to_numpy()
    high = mid["high"].to_numpy()
    low = mid["low"].to_numpy()
    close = mid["close"].to_numpy()
    open_ = mid["open"].to_numpy()

    entry_max, entry_min = _rolling_extremes(high, low, ENTRY_CHANNEL_D1)
    trail_max, trail_min = _rolling_extremes(high, low, TRAIL_CHANNEL_D1)
    atr = _rolling_atr(high, low, close, ATR_PERIOD_D1)

    slippage = _slippage_price(config.symbol)

    logs: list[TradeLog] = []
    for fold in folds:
        tl = TradeLog(engine_id=config.engine_id, fold_id=fold.fold_id)
        n = len(mid)
        i = max(ENTRY_CHANNEL_D1, TRAIL_CHANNEL_D1, ATR_PERIOD_D1)
        while i < n - 1:
            if ts_ns[i] < fold.oos_start:
                i += 1
                continue
            if ts_ns[i] >= fold.oos_end:
                break
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
            n_atr = float(atr[entry_idx - 1])  # N measured at signal bar
            if not np.isfinite(n_atr) or n_atr <= 0:
                i = entry_idx
                continue

            if side == "long":
                entry_price = float(open_[entry_idx]) + slippage
                initial_sl = entry_price - SL_ATR_MULT * n_atr
            else:
                entry_price = float(open_[entry_idx]) - slippage
                initial_sl = entry_price + SL_ATR_MULT * n_atr
            r_dist = SL_ATR_MULT * n_atr

            exit_idx = None
            exit_price = None
            exit_reason = None
            current_sl = initial_sl
            for j in range(entry_idx, n):
                if ts_ns[j] >= fold.oos_end:
                    exit_idx = j
                    exit_price = float(close[j])
                    exit_reason = "FOLD_END"
                    break
                # Trailing channel exit (only tightening in trade direction).
                if j > entry_idx:
                    if side == "long" and np.isfinite(trail_min[j]):
                        current_sl = max(current_sl, float(trail_min[j]))
                    elif side == "short" and np.isfinite(trail_max[j]):
                        current_sl = min(current_sl, float(trail_max[j]))
                if side == "long":
                    if low[j] <= current_sl:
                        exit_idx = j
                        exit_price = current_sl
                        exit_reason = "SL" if current_sl == initial_sl else "TRAIL"
                        break
                else:
                    if high[j] >= current_sl:
                        exit_idx = j
                        exit_price = current_sl
                        exit_reason = "SL" if current_sl == initial_sl else "TRAIL"
                        break
            if exit_idx is None:
                exit_idx = n - 1
                exit_price = float(close[-1])
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
                "sl": float(initial_sl),
                "exit_reason": exit_reason,
                "r_dist": float(r_dist),
                "pnl_r": float(pnl_r),
                "pnl_cash": 0.0,
            }
            tl.trades.append(trade)
            i = exit_idx + 1
        logs.append(tl)
    return logs
