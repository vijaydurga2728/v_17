"""Connors RSI(2) mean-reversion runner (cycle 4, S3). FX-only.

Entry triggers on H1 close:
  RSI(2) < LONG_THRESHOLD  -> long  at next H1 open + slippage.
  RSI(2) > SHORT_THRESHOLD -> short at next H1 open - slippage.

Exit (whichever first):
  - RSI(2) crosses back through EXIT_MID (50) in the trade's favor.
  - TIME_CAP_H1 bars elapse.
  - SL = 2 x ATR_14(H1) adverse (static).

No pyramiding. Only one open position per engine-instrument.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from v17.backtest.engine_runner import TradeLog, _to_mid_bars
from v17.backtest.walkforward import Fold
from v17.common.instrument_spec import pip_size
from v17.setups.rsi2_constants import (
    ATR_PERIOD_H1,
    COST_SLIPPAGE_PIPS_FX,
    EXIT_MID,
    LONG_THRESHOLD,
    RSI_PERIOD_H1,
    SHORT_THRESHOLD,
    SL_ATR_MULT,
    TIME_CAP_H1,
)
from v17.setups.rsi2_engines import RSI2EngineConfig


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


def _rsi_wilder(close: np.ndarray, period: int) -> np.ndarray:
    """Wilder-smoothed RSI."""
    n = len(close)
    rsi = np.full(n, np.nan, dtype=float)
    if n < period + 1:
        return rsi
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    # Seed with simple average over first `period` deltas (indices 1..period).
    avg_gain = gain[1:period + 1].mean()
    avg_loss = loss[1:period + 1].mean()
    for i in range(period, n):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gain[i]) / period
            avg_loss = (avg_loss * (period - 1) + loss[i]) / period
        if avg_loss == 0 and avg_gain == 0:
            rsi[i] = 50.0
        elif avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - 100.0 / (1.0 + rs)
    return rsi


def run_rsi2_oos_batch(
    config: RSI2EngineConfig,
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

    rsi = _rsi_wilder(close, RSI_PERIOD_H1)
    atr = _rolling_atr(high, low, close, ATR_PERIOD_H1)

    slippage = COST_SLIPPAGE_PIPS_FX * pip_size(config.symbol)

    logs: list[TradeLog] = []
    for fold in folds:
        tl = TradeLog(engine_id=config.engine_id, fold_id=fold.fold_id)
        n = len(mid)
        i = max(RSI_PERIOD_H1 + 1, ATR_PERIOD_H1)
        while i < n - 1:
            if ts_ns[i] < fold.oos_start:
                i += 1
                continue
            if ts_ns[i] >= fold.oos_end:
                break
            if not np.isfinite(rsi[i]):
                i += 1
                continue

            side = None
            if rsi[i] < LONG_THRESHOLD:
                side = "long"
            elif rsi[i] > SHORT_THRESHOLD:
                side = "short"
            if side is None:
                i += 1
                continue

            entry_idx = i + 1
            if entry_idx >= n:
                break
            atr_h1 = float(atr[i])
            if not np.isfinite(atr_h1) or atr_h1 <= 0:
                i = entry_idx
                continue

            if side == "long":
                entry_price = open_[entry_idx] + slippage
                sl = entry_price - SL_ATR_MULT * atr_h1
            else:
                entry_price = open_[entry_idx] - slippage
                sl = entry_price + SL_ATR_MULT * atr_h1
            r_dist = abs(entry_price - sl)
            if r_dist <= 0:
                i = entry_idx
                continue

            exit_idx = None
            exit_price = None
            exit_reason = None
            for j in range(entry_idx, min(entry_idx + TIME_CAP_H1 + 1, n)):
                if ts_ns[j] >= fold.oos_end:
                    exit_idx = j
                    exit_price = close[j]
                    exit_reason = "FOLD_END"
                    break
                if side == "long":
                    if low[j] <= sl:
                        exit_idx = j
                        exit_price = sl
                        exit_reason = "SL"
                        break
                    if np.isfinite(rsi[j]) and rsi[j] >= EXIT_MID:
                        exit_idx = j
                        exit_price = close[j]
                        exit_reason = "RSI_MID"
                        break
                else:
                    if high[j] >= sl:
                        exit_idx = j
                        exit_price = sl
                        exit_reason = "SL"
                        break
                    if np.isfinite(rsi[j]) and rsi[j] <= EXIT_MID:
                        exit_idx = j
                        exit_price = close[j]
                        exit_reason = "RSI_MID"
                        break
            if exit_idx is None:
                exit_idx = min(entry_idx + TIME_CAP_H1, n - 1)
                exit_price = close[exit_idx]
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
                "sl": float(sl),
                "exit_reason": exit_reason,
                "r_dist": float(r_dist),
                "pnl_r": float(pnl_r),
                "pnl_cash": 0.0,
            }
            tl.trades.append(trade)
            i = exit_idx + 1
        logs.append(tl)
    return logs
