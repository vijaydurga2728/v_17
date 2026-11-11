"""RSI(2) paired-alpha runner (cycle 4B S10).

Independent-confirmation test for RSI2-USATECHIDXUSD edge. Instead of
measuring per-trade pnl_r (dominated by in-trade windows), measures a
daily *alpha stream* against a constant-exposure benchmark:

  active_pos_t = 1.0 when in an RSI(2) trade on bar t, 0 otherwise.
  exposure_frac = mean(active_pos) over the window.
  benchmark_pos_t = exposure_frac   (constant).
  log_ret_t = log(close_t / close_{t-1}).
  alpha_t = (active_pos_t - exposure_frac) * log_ret_t.

Over the window, cumulative alpha = sum(alpha_t). This decomposes drift
from timing by construction: a random-day selection with the same
exposure_frac would produce E[alpha] = 0.

Null test (scheme-1 random-entry): permute which days are "in-trade"
keeping count and average holding period fixed, recompute alpha stream,
compare observed alpha metrics to null distribution.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from v17.backtest.engine_runner import _to_mid_bars
from v17.backtest.rsi2_runner import run_rsi2_oos_batch
from v17.backtest.walkforward import Fold
from v17.setups.rsi2_constants import SMA_EXIT_PERIOD_D1, TIME_CAP_D1
from v17.setups.rsi2_engines import RSI2EngineConfig


@dataclass(frozen=True)
class PairedAlpha:
    observed_alpha_cum: float
    observed_alpha_mean: float
    observed_alpha_pf: float
    exposure_frac: float
    avg_holding_bars: float
    n_trades: int
    n_window_bars: int


def _bar_idx_for_ts(ts_ns: np.ndarray, target: int) -> int:
    """Return index i such that ts_ns[i] == target, else -1."""
    pos = np.searchsorted(ts_ns, target)
    if pos < len(ts_ns) and ts_ns[pos] == target:
        return int(pos)
    return -1


def _mark_active(trades, ts_ns: np.ndarray, window_start: int, window_end: int) -> np.ndarray:
    """Return a boolean array of shape ts_ns indicating in-trade bars."""
    active = np.zeros(len(ts_ns), dtype=bool)
    for t in trades:
        e_i = _bar_idx_for_ts(ts_ns, int(t["ts_entry_ns"]))
        x_i = _bar_idx_for_ts(ts_ns, int(t["ts_exit_ns"]))
        if e_i < 0 or x_i < 0 or e_i > x_i:
            continue
        active[e_i: x_i + 1] = True
    in_window = (ts_ns >= window_start) & (ts_ns < window_end)
    return active & in_window


def _alpha_metrics(active_pos: np.ndarray, log_ret: np.ndarray, in_window: np.ndarray) -> PairedAlpha | None:
    window_bars = int(in_window.sum())
    if window_bars < 10:
        return None
    exposure = float(active_pos[in_window].mean())
    bench_pos = exposure
    alpha_t = np.where(in_window, (active_pos.astype(float) - bench_pos) * log_ret, 0.0)
    alpha_series = alpha_t[in_window]
    cum = float(alpha_series.sum())
    mean = float(alpha_series.mean()) if len(alpha_series) else 0.0
    wins = alpha_series[alpha_series > 0].sum()
    losses = -alpha_series[alpha_series < 0].sum()
    pf = float(wins / losses) if losses > 0 else float("inf")
    # avg holding (bars per trade run) — approximate.
    # Find contiguous active segments.
    transitions = np.diff(active_pos.astype(int), prepend=0)
    starts = np.where(transitions == 1)[0]
    ends = np.where(transitions == -1)[0]
    if len(ends) < len(starts):
        ends = np.concatenate([ends, [len(active_pos)]])
    hold = (ends - starts) if len(starts) else np.array([0])
    avg_hold = float(hold.mean()) if len(hold) else 0.0
    return PairedAlpha(
        observed_alpha_cum=cum, observed_alpha_mean=mean, observed_alpha_pf=pf,
        exposure_frac=exposure, avg_holding_bars=avg_hold,
        n_trades=len(starts), n_window_bars=window_bars,
    )


def compute_paired_alpha(
    config: RSI2EngineConfig,
    bars_d1: pd.DataFrame,
    folds: list[Fold],
    window_start_ns: int,
    window_end_ns: int,
) -> PairedAlpha:
    """Compute observed paired-alpha metrics on the given window."""
    if bars_d1.empty:
        raise ValueError("bars_d1 is empty")
    mid = _to_mid_bars(bars_d1).sort_values("ts_ns").reset_index(drop=True)
    ts_ns = mid["ts_ns"].to_numpy()
    close = mid["close"].to_numpy()
    log_ret = np.diff(np.log(close), prepend=np.log(close[0]))

    logs = run_rsi2_oos_batch(config, bars_d1, folds)
    trades = [t for l in logs for t in l.trades]
    active = _mark_active(trades, ts_ns, window_start_ns, window_end_ns)
    in_window = (ts_ns >= window_start_ns) & (ts_ns < window_end_ns)
    metrics = _alpha_metrics(active, log_ret, in_window)
    if metrics is None:
        raise ValueError("insufficient window bars")
    return metrics
