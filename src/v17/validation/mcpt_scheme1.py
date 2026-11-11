"""MCPT scheme 1 — signal-time permutation with engine re-run.

Under-powered pnl_bootstrap (scheme 2) cannot discriminate PF; this
scheme does the real test:

  For each of n_permutations:
    1. Sample N_obs random entry bar indices from eligible pool
       (without replacement, uniform).
    2. For each sampled bar, apply the engine's long-only exit rule
       (close > SMA(5) or TIME_CAP_D1) to produce a synthetic trade.
    3. Record synthetic PF.
  Compare observed PF to the null distribution.

This is specific to the RSI(2) long-only runner for cycle 4B. Generic
scheme-1 for all strategies is out of scope — build per-strategy when
each one is due for live-money qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from v17.backtest.engine_runner import _to_mid_bars
from v17.backtest.rsi2_runner import _rsi_wilder, _sma
from v17.setups.rsi2_constants import (
    COST_SLIPPAGE_PTS_USATECH,
    RSI_PERIOD_D1,
    SMA_EXIT_PERIOD_D1,
    TIME_CAP_D1,
)
from v17.validation.seeds import permutation_seed


@dataclass(frozen=True)
class Scheme1Result:
    engine_id: str
    window_label: str
    observed_pf: float
    n_permutations: int
    n_obs_trades: int
    null_pf_mean: float
    null_pf_median: float
    null_pf_p95: float
    p_pf: float
    p_sharpe: float


def _pf(pnl: np.ndarray) -> float:
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    if losses <= 0:
        return float("inf")
    return float(wins / losses)


def _sharpe(pnl: np.ndarray) -> float:
    if len(pnl) < 2:
        return 0.0
    std = pnl.std(ddof=1)
    if std == 0:
        return 0.0
    return float(pnl.mean() / std * np.sqrt(252))


def _simulate_one_long_trade(
    entry_idx: int,
    open_: np.ndarray,
    close: np.ndarray,
    sma5: np.ndarray,
    ts_ns: np.ndarray,
    slippage: float,
    n_bars: int,
) -> float | None:
    """Apply RSI(2) long-only exit rule from a given entry index.

    Returns pnl_r using r_dist = close[signal] * 0.01 convention (matches runner).
    `entry_idx` here is the signal bar; actual entry is entry_idx + 1 open.
    """
    actual_entry = entry_idx + 1
    if actual_entry >= n_bars:
        return None
    entry_price = float(open_[actual_entry]) + slippage
    r_dist = max(float(close[entry_idx]) * 0.01, 1e-9)

    exit_price = None
    for j in range(actual_entry, min(actual_entry + TIME_CAP_D1 + 1, n_bars)):
        if np.isfinite(sma5[j]) and close[j] > sma5[j]:
            exit_price = float(close[j])
            break
    if exit_price is None:
        if actual_entry + TIME_CAP_D1 < n_bars:
            exit_price = float(close[actual_entry + TIME_CAP_D1])
        else:
            exit_price = float(close[-1])

    pnl_abs = exit_price - entry_price
    return pnl_abs / r_dist


def run_scheme1_mcpt_rsi2(
    engine_id: str,
    bars_d1: pd.DataFrame,
    observed_trades: pd.DataFrame,
    window_label: str,
    window_start_ns: int,
    window_end_ns: int,
    n_permutations: int = 500,
    out_root: Path | None = None,
) -> Scheme1Result:
    """Compute scheme-1 MCPT p-value for RSI(2) long-only on a given window.

    bars_d1: full D1 bars for the window symbol (any range covering window).
    observed_trades: DataFrame with pnl_r + ts_entry_ns, restricted to this window.
    """
    if bars_d1.empty:
        raise ValueError("bars_d1 is empty")
    if observed_trades.empty:
        raise ValueError("observed_trades is empty")

    mid = _to_mid_bars(bars_d1).sort_values("ts_ns").reset_index(drop=True)
    ts_ns = mid["ts_ns"].to_numpy()
    open_ = mid["open"].to_numpy()
    close = mid["close"].to_numpy()

    sma5 = _sma(close, SMA_EXIT_PERIOD_D1)

    # Eligible entry bars: in-window, enough history, enough forward room.
    n = len(mid)
    in_window = (ts_ns >= window_start_ns) & (ts_ns < window_end_ns)
    min_i = max(RSI_PERIOD_D1 + 1, SMA_EXIT_PERIOD_D1)
    max_i = n - 2  # need at least 1 forward bar to fill
    eligible_mask = in_window.copy()
    eligible_mask[:min_i] = False
    eligible_mask[max_i + 1:] = False
    eligible_idx = np.where(eligible_mask)[0]
    if len(eligible_idx) == 0:
        raise ValueError("no eligible entry bars in window")

    n_obs = int(len(observed_trades))
    if n_obs > len(eligible_idx):
        raise ValueError(
            f"observed trades ({n_obs}) exceed eligible pool ({len(eligible_idx)})"
        )

    observed_pnl_r = observed_trades["pnl_r"].to_numpy()
    observed_pf = _pf(observed_pnl_r)
    observed_sharpe = _sharpe(observed_pnl_r)

    slippage = COST_SLIPPAGE_PTS_USATECH

    null_pf = np.full(n_permutations, np.nan)
    null_sharpe = np.full(n_permutations, np.nan)
    for p in range(n_permutations):
        seed = permutation_seed(engine_id, f"scheme1_{window_label}", p)
        rng = np.random.default_rng(seed)
        sampled = rng.choice(eligible_idx, size=n_obs, replace=False)
        pnls = []
        for ei in sampled:
            r = _simulate_one_long_trade(int(ei), open_, close, sma5, ts_ns, slippage, n)
            if r is not None and np.isfinite(r):
                pnls.append(r)
        if not pnls:
            continue
        arr = np.array(pnls)
        null_pf[p] = _pf(arr)
        null_sharpe[p] = _sharpe(arr)

    finite_pf = null_pf[np.isfinite(null_pf)]
    finite_sh = null_sharpe[np.isfinite(null_sharpe)]
    p_pf = float((finite_pf >= observed_pf).mean()) if len(finite_pf) else float("nan")
    p_sh = float((finite_sh >= observed_sharpe).mean()) if len(finite_sh) else float("nan")

    result = Scheme1Result(
        engine_id=engine_id,
        window_label=window_label,
        observed_pf=observed_pf,
        n_permutations=n_permutations,
        n_obs_trades=n_obs,
        null_pf_mean=float(np.nanmean(null_pf)),
        null_pf_median=float(np.nanmedian(null_pf)),
        null_pf_p95=float(np.nanpercentile(finite_pf, 95)) if len(finite_pf) else float("nan"),
        p_pf=p_pf,
        p_sharpe=p_sh,
    )

    if out_root is not None:
        out = Path(out_root) / "mcpt_scheme1" / engine_id / window_label / "null_distribution.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({
            "perm_idx": np.arange(n_permutations),
            "null_pf": null_pf,
            "null_sharpe": null_sharpe,
        }).to_parquet(out, index=False)

    return result
