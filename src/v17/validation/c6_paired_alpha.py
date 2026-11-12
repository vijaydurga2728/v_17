"""Cycle 6 paired-alpha ablation nulls: random, regime-only, micro-only."""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from v17.backtest.c6_runner import run_backtest
from v17.setups.c6_regime import compute_regime
from v17.validation.c6_gates import _sharpe_from_trades


def paired_alpha(obs_tl: pd.DataFrame, null_tl: pd.DataFrame, seed: int, n_bootstrap: int = 1000) -> float:
    rng = np.random.default_rng(seed)
    obs_pnl = obs_tl["net_pnl_usd"].to_numpy()
    null_pnl = null_tl["net_pnl_usd"].to_numpy()
    obs_sharpe = _sharpe_from_trades(obs_pnl)
    null_sharpe = _sharpe_from_trades(null_pnl)
    diff_obs = obs_sharpe - null_sharpe
    pooled = np.concatenate([obs_pnl, null_pnl])
    n_o, n_n = len(obs_pnl), len(null_pnl)
    diffs = np.empty(n_bootstrap, dtype=float)
    for i in range(n_bootstrap):
        perm = rng.permutation(pooled)
        a, b = perm[:n_o], perm[n_o:n_o + n_n]
        diffs[i] = _sharpe_from_trades(a) - _sharpe_from_trades(b)
    p = float((diffs >= diff_obs).sum() + 1) / (n_bootstrap + 1)
    return p


def null_random_entries(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    params: dict,
    equity: float,
    n_trades_per_sym_dir: dict,
    seed: int,
) -> pd.DataFrame:
    """Null-A: sample random M5 entry bars per (symbol, direction) matching observed counts.

    Exits follow the normal position state-machine. Returns a trade log in same schema.
    """
    rng = np.random.default_rng(seed)

    def override(sym: str, sig_df: pd.DataFrame) -> pd.DataFrame:
        n_long = n_trades_per_sym_dir.get((sym, "long"), 0)
        n_short = n_trades_per_sym_dir.get((sym, "short"), 0)
        sig_df = sig_df.copy()
        sig_df["confirm_long"] = False
        sig_df["confirm_short"] = False
        idx_long = rng.choice(len(sig_df), size=min(n_long, len(sig_df)), replace=False)
        sig_df.loc[sig_df.index[idx_long], "confirm_long"] = True
        remaining = sig_df.index.difference(sig_df.index[idx_long])
        idx_short = rng.choice(len(remaining), size=min(n_short, len(remaining)), replace=False)
        sig_df.loc[remaining[idx_short], "confirm_short"] = True
        return sig_df

    tl, _ = run_backtest(
        spx_m5, fx_m5_by_sym, calendar_idx, params, equity,
        start_ts_ns=spx_m5["ts_utc"].min(), end_ts_ns=spx_m5["ts_utc"].max(),
        signal_override=override,
    )
    return tl


def null_regime_only(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    params: dict,
    equity: float,
    seed: int,
) -> pd.DataFrame:
    """Null-B: retain regime signal but replace micro-trigger with regime flip bars only."""
    reg = compute_regime(
        spx_m5, k_atr=params["K"], slope_window=params["slope_window"]
    ).set_index("ts_utc")
    flips = reg["regime_state"].shift(1) != reg["regime_state"]
    long_bars = reg.index[flips & (reg["regime_state"] == "LONG_BIAS")]
    short_bars = reg.index[flips & (reg["regime_state"] == "SHORT_BIAS")]

    def override(sym: str, sig_df: pd.DataFrame) -> pd.DataFrame:
        sig_df = sig_df.copy()
        sig_df["confirm_long"] = sig_df["ts_utc"].isin(long_bars)
        sig_df["confirm_short"] = sig_df["ts_utc"].isin(short_bars)
        return sig_df

    tl, _ = run_backtest(
        spx_m5, fx_m5_by_sym, calendar_idx, params, equity,
        start_ts_ns=spx_m5["ts_utc"].min(), end_ts_ns=spx_m5["ts_utc"].max(),
        signal_override=override,
    )
    return tl


def null_micro_only(
    spx_m5: pd.DataFrame,
    fx_m5_by_sym: Mapping[str, pd.DataFrame],
    calendar_idx: pd.DataFrame,
    params: dict,
    equity: float,
    seed: int,
) -> pd.DataFrame:
    """Null-C: micro-trigger passes through but regime is always permissive.

    Constructs a strongly-trending synthetic SPX so regime == LONG_BIAS throughout,
    runs the backtest to collect long-side micro trades. Repeats with a downtrending
    SPX for short-side micro trades. Concatenates both trade logs.
    """
    spx_fake = spx_m5.copy()
    n = len(spx_fake)
    # Force strictly monotonic uptrend so regime stays LONG_BIAS for longs.
    spx_fake["bid_c"] = np.linspace(1000.0, 1_000_000.0, n)
    spx_fake["ask_c"] = spx_fake["bid_c"] + 0.1
    spx_fake["bid_h"] = spx_fake["bid_c"]
    spx_fake["ask_h"] = spx_fake["ask_c"]
    spx_fake["bid_l"] = spx_fake["bid_c"]
    spx_fake["ask_l"] = spx_fake["ask_c"]
    spx_fake["bid_o"] = spx_fake["bid_c"]
    spx_fake["ask_o"] = spx_fake["ask_c"]

    tl_long, _ = run_backtest(
        spx_fake, fx_m5_by_sym, calendar_idx, params, equity,
        start_ts_ns=spx_m5["ts_utc"].min(), end_ts_ns=spx_m5["ts_utc"].max(),
        signal_override=None,
    )

    # Downtrending SPX forces SHORT_BIAS for short-side micro trades.
    spx_down = spx_fake.copy()
    price_cols = ["bid_c", "ask_c", "bid_h", "ask_h", "bid_l", "ask_l", "bid_o", "ask_o"]
    spx_down[price_cols] = spx_fake[price_cols].iloc[::-1].values

    tl_short, _ = run_backtest(
        spx_down, fx_m5_by_sym, calendar_idx, params, equity,
        start_ts_ns=spx_m5["ts_utc"].min(), end_ts_ns=spx_m5["ts_utc"].max(),
        signal_override=None,
    )
    return pd.concat([tl_long, tl_short], ignore_index=True)
