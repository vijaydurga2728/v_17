"""Connors RSI(2) runner.

Cycle 4B (2026-11-11, [P-HACK-ACKNOWLEDGED]): rewritten to D1 long-only on
USATECHIDXUSD per Connors spec. See docs/superpowers/specs/2026-11-11-cycle4b-correction-prereg.md § 3 S3.

Entry: on D1 close, if RSI(2) < 10 -> long at NEXT D1 open + slippage.
Exit (whichever first):
  - Close > SMA(5) (Connors exit rule).
  - TIME_CAP_D1 bars elapsed (safety; Connors uses no cap but we bound it).
No stop-loss (Connors spec).

R-size: distance from entry to the day-before-entry close as a proxy for the
         "oversold" extent; used only to normalize pnl_r. Not a trading stop.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.backtest.engine_runner import TradeLog, _to_mid_bars
from v17.backtest.walkforward import Fold
from v17.setups.rsi2_constants import (
    COST_SLIPPAGE_PTS_USATECH,
    LONG_THRESHOLD,
    RSI_PERIOD_D1,
    SMA_EXIT_PERIOD_D1,
    TIME_CAP_D1,
)
from v17.setups.rsi2_engines import RSI2EngineConfig


def _rsi_wilder(close: np.ndarray, period: int) -> np.ndarray:
    n = len(close)
    rsi = np.full(n, np.nan, dtype=float)
    if n < period + 1:
        return rsi
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
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


def _sma(x: np.ndarray, period: int) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan, dtype=float)
    if n < period:
        return out
    cum = np.cumsum(x)
    out[period - 1] = cum[period - 1] / period
    for i in range(period, n):
        out[i] = (cum[i] - cum[i - period]) / period
    return out


def run_rsi2_oos_batch(
    config: RSI2EngineConfig,
    bars_d1: pd.DataFrame,
    folds: list[Fold],
) -> list[TradeLog]:
    if bars_d1.empty:
        return [TradeLog(engine_id=config.engine_id, fold_id=f.fold_id) for f in folds]

    mid = _to_mid_bars(bars_d1).sort_values("ts_ns").reset_index(drop=True)
    ts_ns = mid["ts_ns"].to_numpy()
    close = mid["close"].to_numpy()
    open_ = mid["open"].to_numpy()

    rsi = _rsi_wilder(close, RSI_PERIOD_D1)
    sma5 = _sma(close, SMA_EXIT_PERIOD_D1)

    slippage = COST_SLIPPAGE_PTS_USATECH  # NAS100-only this cycle

    logs: list[TradeLog] = []
    for fold in folds:
        tl = TradeLog(engine_id=config.engine_id, fold_id=fold.fold_id)
        n = len(mid)
        i = max(RSI_PERIOD_D1 + 1, SMA_EXIT_PERIOD_D1)
        while i < n - 1:
            if ts_ns[i] < fold.oos_start:
                i += 1
                continue
            if ts_ns[i] >= fold.oos_end:
                break
            if not np.isfinite(rsi[i]):
                i += 1
                continue
            # Long-only Connors entry.
            if rsi[i] >= LONG_THRESHOLD:
                i += 1
                continue

            entry_idx = i + 1
            if entry_idx >= n:
                break
            entry_price = float(open_[entry_idx]) + slippage

            # R-normalization proxy: signal-bar range (fixed positive value).
            # Not a stop — Connors has no SL. This just makes pnl_r comparable
            # across trades/days of different vol.
            r_dist = max(float(close[i] - close[i - 1]) * -1.0 if close[i] < close[i - 1] else 1.0, 1.0)
            # Simpler: use absolute bar-i price as 1% of price unit so pnl_r is
            # (pnl_abs / (close[i] * 0.01)).
            r_dist = max(close[i] * 0.01, 1e-9)

            exit_idx = None
            exit_price = None
            exit_reason = None
            for j in range(entry_idx, min(entry_idx + TIME_CAP_D1 + 1, n)):
                if ts_ns[j] >= fold.oos_end:
                    exit_idx = j
                    exit_price = float(close[j])
                    exit_reason = "FOLD_END"
                    break
                if np.isfinite(sma5[j]) and close[j] > sma5[j]:
                    exit_idx = j
                    exit_price = float(close[j])
                    exit_reason = "SMA_EXIT"
                    break
            if exit_idx is None:
                exit_idx = min(entry_idx + TIME_CAP_D1, n - 1)
                exit_price = float(close[exit_idx])
                exit_reason = "TIME_CAP"

            pnl_abs = exit_price - entry_price
            pnl_r = pnl_abs / r_dist if r_dist > 0 else 0.0

            trade = {
                "engine_id": config.engine_id,
                "fold_id": fold.fold_id,
                "symbol": config.symbol,
                "ts_entry_ns": int(ts_ns[entry_idx]),
                "ts_exit_ns": int(ts_ns[exit_idx]),
                "side": "long",
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "exit_reason": exit_reason,
                "r_dist": float(r_dist),
                "pnl_r": float(pnl_r),
                "pnl_cash": 0.0,
            }
            tl.trades.append(trade)
            i = exit_idx + 1
        logs.append(tl)
    return logs
