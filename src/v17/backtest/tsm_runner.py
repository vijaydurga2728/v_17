"""Time-Series Momentum runner (cycle 4, S1).

Rebalance cadence: every HOLD_H1 bars (120 H1 = ~5 trading days).
Entry: at the first H1 bar on/after the rebalance boundary.
  Signal: sign of (close[t] - close[t - LOOKBACK_H1]).
  side = "long" if signal > 0 else "short".
Stop: 2 × ATR_14(H1), static from entry.
Target: 3R opposite target, static.
Exit: whichever first — SL, TP, hold-period cap (HOLD_H1 bars post-entry).

Per-symbol preprocessing runs ONCE (ATR_14, mid bars, rebalance index list).
Fold loop slices by index — no concat.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from v17.backtest.engine_runner import TradeLog, _to_mid_bars
from v17.backtest.fills import simulate_fill_market
from v17.backtest.walkforward import Fold
from v17.common.instrument_spec import pip_size
from v17.setups.tsm_constants import (
    ATR_PERIOD_H1,
    COST_SLIPPAGE_PIPS_FX,
    COST_SLIPPAGE_PTS,
    HOLD_H1,
    LOOKBACK_H1,
    SL_ATR_MULT,
    TARGET_R,
)
from v17.setups.tsm_engines import TSMEngineConfig


_H1_NS = 3_600_000_000_000


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
    # FX: convert pips to price units.
    return COST_SLIPPAGE_PIPS_FX * pip_size(symbol)


def run_tsm_oos_batch(
    config: TSMEngineConfig,
    bars_h1: pd.DataFrame,
    folds: list[Fold],
) -> list[TradeLog]:
    """Run TSM engine over N folds on H1 bars.

    bars_h1 must be paired bid/ask H1 bars with columns (ts_utc, bid_*, ask_*, ...).
    """
    if bars_h1.empty:
        return [TradeLog(engine_id=config.engine_id, fold_id=f.fold_id) for f in folds]

    mid = _to_mid_bars(bars_h1).sort_values("ts_ns").reset_index(drop=True)
    ts_ns = mid["ts_ns"].to_numpy()
    close = mid["close"].to_numpy()
    high = mid["high"].to_numpy()
    low = mid["low"].to_numpy()

    atr = _rolling_atr(high, low, close, ATR_PERIOD_H1)

    # Rebalance anchor indices: every HOLD_H1 bars after the first eligible index
    # (needs LOOKBACK_H1 bars of history AND ATR_PERIOD_H1 bars behind).
    first_eligible = max(LOOKBACK_H1, ATR_PERIOD_H1)
    rebalance_idx = list(range(first_eligible, len(mid), HOLD_H1))

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

            lookback_return = close[r_idx] - close[r_idx - LOOKBACK_H1]
            if lookback_return == 0 or not np.isfinite(lookback_return):
                continue
            side = "long" if lookback_return > 0 else "short"

            atr_h1 = float(atr[r_idx])
            if not np.isfinite(atr_h1) or atr_h1 <= 0:
                continue

            entry_est = float(close[r_idx])
            sl_dist = SL_ATR_MULT * atr_h1
            tp_dist = TARGET_R * sl_dist

            if side == "long":
                sl = entry_est - sl_dist
                tp = entry_est + tp_dist
            else:
                sl = entry_est + sl_dist
                tp = entry_est - tp_dist

            # Build day/hold slice from rebalance index forward, capped at HOLD_H1.
            end_idx = min(r_idx + HOLD_H1, len(mid) - 1)
            slice_df = mid.iloc[r_idx: end_idx + 1].reset_index(drop=True)
            if len(slice_df) < 2:
                continue
            time_cap_ns = int(ts_ns[end_idx] - ts_ns[r_idx])

            fill = simulate_fill_market(
                bars=slice_df,
                entry_idx=0,
                side=side,
                sl=sl,
                tp=tp,
                time_cap_ns=time_cap_ns,
                slippage_pts=slippage,
            )

            entry_price = fill["entry_price"]
            exit_price = fill["exit_price"]
            r_dist = sl_dist
            if side == "long":
                pnl_abs = exit_price - entry_price
            else:
                pnl_abs = entry_price - exit_price
            pnl_r = pnl_abs / r_dist if r_dist > 0 else 0.0

            trade = {
                "engine_id": config.engine_id,
                "fold_id": fold.fold_id,
                "symbol": config.symbol,
                "ts_entry_ns": int(ts_ns[r_idx]),
                "ts_exit_ns": int(ts_ns[r_idx + fill["exit_idx"]]),
                "side": side,
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
