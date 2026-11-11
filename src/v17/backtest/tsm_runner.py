"""Time-Series Momentum runner.

Cycle 4B (2026-11-11, [P-HACK-ACKNOWLEDGED]): rewritten to D1 per Moskowitz
paper time-series arm. See docs/superpowers/specs/2026-11-11-cycle4b-correction-prereg.md.

Rebalance cadence: every HOLD_D1 bars (21 D1 ≈ 1 month).
Entry: at the first D1 bar on/after the rebalance boundary.
  Signal: sign of (close[t] - close[t - LOOKBACK_D1]).
  side = "long" if signal > 0 else "short".
Stop: 2 × ATR_14(D1), static from entry.
Target: NONE. Exit on SL touch OR hold-period cap.

Per-symbol preprocessing runs ONCE (ATR_14, mid bars, rebalance index list).
Fold loop slices by index — no concat.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.backtest.engine_runner import TradeLog, _to_mid_bars
from v17.backtest.walkforward import Fold
from v17.common.instrument_spec import pip_size
from v17.setups.tsm_constants import (
    ATR_PERIOD_D1,
    COST_SLIPPAGE_PIPS_FX,
    COST_SLIPPAGE_PTS,
    HOLD_D1,
    LOOKBACK_D1,
    SL_ATR_MULT,
)
from v17.setups.tsm_engines import TSMEngineConfig


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


def _slippage_price(symbol: str) -> float:
    if symbol in COST_SLIPPAGE_PTS:
        return COST_SLIPPAGE_PTS[symbol]
    return COST_SLIPPAGE_PIPS_FX * pip_size(symbol)


def run_tsm_oos_batch(
    config: TSMEngineConfig,
    bars_d1: pd.DataFrame,
    folds: list[Fold],
) -> list[TradeLog]:
    """Run TSM engine over N folds on D1 bars.

    bars_d1 must be paired bid/ask D1 bars with columns (ts_utc, bid_*, ask_*, ...).
    """
    if bars_d1.empty:
        return [TradeLog(engine_id=config.engine_id, fold_id=f.fold_id) for f in folds]

    mid = _to_mid_bars(bars_d1).sort_values("ts_ns").reset_index(drop=True)
    ts_ns = mid["ts_ns"].to_numpy()
    close = mid["close"].to_numpy()
    high = mid["high"].to_numpy()
    low = mid["low"].to_numpy()
    open_ = mid["open"].to_numpy()

    atr = _rolling_atr(high, low, close, ATR_PERIOD_D1)

    first_eligible = max(LOOKBACK_D1, ATR_PERIOD_D1)
    rebalance_idx = list(range(first_eligible, len(mid), HOLD_D1))

    slippage = _slippage_price(config.symbol)

    logs: list[TradeLog] = []
    for fold in folds:
        tl = TradeLog(engine_id=config.engine_id, fold_id=fold.fold_id)
        fold_mask = (ts_ns >= fold.oos_start) & (ts_ns < fold.oos_end)
        if not fold_mask.any():
            logs.append(tl)
            continue

        for r_idx in rebalance_idx:
            if r_idx >= len(mid):
                break
            if ts_ns[r_idx] < fold.oos_start or ts_ns[r_idx] >= fold.oos_end:
                continue

            lookback_return = close[r_idx] - close[r_idx - LOOKBACK_D1]
            if lookback_return == 0 or not np.isfinite(lookback_return):
                continue
            side = "long" if lookback_return > 0 else "short"

            atr_d1 = float(atr[r_idx])
            if not np.isfinite(atr_d1) or atr_d1 <= 0:
                continue

            # Enter on NEXT bar open to avoid lookahead on signal day.
            entry_idx = r_idx + 1
            if entry_idx >= len(mid):
                break

            if side == "long":
                entry_price = float(open_[entry_idx]) + slippage
                sl = entry_price - SL_ATR_MULT * atr_d1
            else:
                entry_price = float(open_[entry_idx]) - slippage
                sl = entry_price + SL_ATR_MULT * atr_d1
            r_dist = SL_ATR_MULT * atr_d1

            end_idx = min(entry_idx + HOLD_D1, len(mid) - 1)
            exit_idx = None
            exit_price = None
            exit_reason = None
            for j in range(entry_idx, end_idx + 1):
                if ts_ns[j] >= fold.oos_end:
                    exit_idx = j
                    exit_price = float(close[j])
                    exit_reason = "FOLD_END"
                    break
                if side == "long":
                    if low[j] <= sl:
                        exit_idx = j
                        exit_price = sl
                        exit_reason = "SL"
                        break
                else:
                    if high[j] >= sl:
                        exit_idx = j
                        exit_price = sl
                        exit_reason = "SL"
                        break
            if exit_idx is None:
                exit_idx = end_idx
                exit_price = float(close[exit_idx])
                exit_reason = "HOLD_END"

            if side == "long":
                pnl_abs = exit_price - entry_price
            else:
                pnl_abs = entry_price - exit_price
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
        logs.append(tl)
    return logs
