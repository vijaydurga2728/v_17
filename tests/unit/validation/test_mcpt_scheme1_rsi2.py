"""Scheme-1 MCPT tests (RSI(2) random-entry null)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.validation.mcpt_scheme1 import run_scheme1_mcpt_rsi2


_D1_NS = 86_400_000_000_000


def _d1_bars(n: int, symbol: str = "USATECHIDXUSD") -> pd.DataFrame:
    base = pd.Timestamp("2015-01-01", tz="UTC").value
    ts = base + np.arange(n, dtype=np.int64) * _D1_NS
    rng = np.random.default_rng(42)
    rets = rng.normal(0.0005, 0.01, n)
    mid = 15000.0 * np.exp(np.cumsum(rets))
    half_spread = 0.0005 * mid[0]
    w = mid * 0.005
    return pd.DataFrame({
        "ts_utc": ts,
        "symbol": [symbol] * n,
        "bid_o": mid - half_spread,
        "bid_h": mid - half_spread + w,
        "bid_l": mid - half_spread - w,
        "bid_c": mid - half_spread,
        "ask_o": mid + half_spread,
        "ask_h": mid + half_spread + w,
        "ask_l": mid + half_spread - w,
        "ask_c": mid + half_spread,
        "bid_volume": np.full(n, 10.0),
        "ask_volume": np.full(n, 10.0),
        "spread_mid": np.full(n, 2 * half_spread),
    })


def test_scheme1_returns_p_in_unit_interval():
    bars = _d1_bars(400)
    ts = bars["ts_utc"].to_numpy()
    trades = pd.DataFrame({
        "pnl_r": np.random.default_rng(0).normal(0.1, 1.0, 30),
        "ts_entry_ns": ts[50:50 + 30].astype(np.int64),
    })
    res = run_scheme1_mcpt_rsi2(
        engine_id="RSI2-USATECHIDXUSD", bars_d1=bars,
        observed_trades=trades, window_label="test",
        window_start_ns=int(ts[0]), window_end_ns=int(ts[-1] + _D1_NS),
        n_permutations=50,
    )
    assert 0.0 <= res.p_pf <= 1.0
    assert res.n_obs_trades == 30
    assert res.n_permutations == 50


def test_scheme1_detects_strong_observed_edge():
    bars = _d1_bars(400)
    ts = bars["ts_utc"].to_numpy()
    trades = pd.DataFrame({
        "pnl_r": np.array([2.0] * 25 + [-0.5] * 5),
        "ts_entry_ns": ts[50:80].astype(np.int64),
    })
    res = run_scheme1_mcpt_rsi2(
        engine_id="RSI2-USATECHIDXUSD", bars_d1=bars,
        observed_trades=trades, window_label="test_strong",
        window_start_ns=int(ts[0]), window_end_ns=int(ts[-1] + _D1_NS),
        n_permutations=100,
    )
    assert res.observed_pf > 5.0
    # Small-sample (n=30, rand-walk bars) produces wide null PF distribution;
    # p_pf < 0.15 is a reasonable floor for a clearly-strong edge.
    assert res.p_pf < 0.15


def test_scheme1_raises_on_empty_trades():
    bars = _d1_bars(200)
    with pytest.raises(ValueError):
        run_scheme1_mcpt_rsi2(
            engine_id="RSI2-USATECHIDXUSD", bars_d1=bars,
            observed_trades=pd.DataFrame(columns=["pnl_r", "ts_entry_ns"]),
            window_label="empty",
            window_start_ns=0, window_end_ns=10,
            n_permutations=10,
        )
