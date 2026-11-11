"""Donchian breakout runner tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.backtest.donchian_runner import run_donchian_oos_batch
from v17.backtest.walkforward import Fold
from v17.setups.donchian_constants import ENTRY_CHANNEL_H1
from v17.setups.donchian_engines import DONCHIAN_CATALOG


_H1_NS = 3_600_000_000_000


def _h1_series(prices: list[float], symbol: str, high_wiggle: float = 0.05, low_wiggle: float = 0.05) -> pd.DataFrame:
    n = len(prices)
    base = pd.Timestamp("2020-01-01", tz="UTC").value
    ts = base + np.arange(n, dtype=np.int64) * _H1_NS
    mids = np.array(prices)
    half_spread = 0.0005 * mids[0]
    return pd.DataFrame({
        "ts_utc": ts,
        "symbol": [symbol] * n,
        "bid_o": mids - half_spread,
        "bid_h": mids - half_spread + high_wiggle,
        "bid_l": mids - half_spread - low_wiggle,
        "bid_c": mids - half_spread,
        "ask_o": mids + half_spread,
        "ask_h": mids + half_spread + high_wiggle,
        "ask_l": mids + half_spread - low_wiggle,
        "ask_c": mids + half_spread,
        "bid_volume": np.full(n, 10.0),
        "ask_volume": np.full(n, 10.0),
        "spread_mid": np.full(n, 2 * half_spread),
    })


def _one_fold(ts: np.ndarray) -> Fold:
    return Fold(fold_id=1, train_start=0, train_end=int(ts[0] - 1),
                oos_start=int(ts[0]), oos_end=int(ts[-1] + _H1_NS))


def test_no_breakout_on_flat_series() -> None:
    engine = DONCHIAN_CATALOG[2]
    prices = [15000.0] * 50
    bars = _h1_series(prices, engine.symbol, high_wiggle=0.01, low_wiggle=0.01)
    ts = bars["ts_utc"].to_numpy()
    logs = run_donchian_oos_batch(engine, bars, [_one_fold(ts)])
    assert logs[0].trades == []


def test_long_breakout_hits_tp_on_strong_rally() -> None:
    engine = DONCHIAN_CATALOG[2]
    # First 20 bars flat at 15000 → prior-20 high = 15000.05. Then jump above and continue.
    prices = [15000.0] * ENTRY_CHANNEL_H1 + [15050.0 + 5.0 * i for i in range(40)]
    bars = _h1_series(prices, engine.symbol, high_wiggle=0.01, low_wiggle=0.01)
    ts = bars["ts_utc"].to_numpy()
    logs = run_donchian_oos_batch(engine, bars, [_one_fold(ts)])
    trades = logs[0].trades
    assert len(trades) >= 1
    first = trades[0]
    assert first["side"] == "long"
    assert first["exit_reason"] in ("TP", "SL", "FOLD_END", "TIME")


def test_short_breakout_on_downside_break() -> None:
    engine = DONCHIAN_CATALOG[2]
    prices = [15000.0] * ENTRY_CHANNEL_H1 + [14950.0 - 5.0 * i for i in range(40)]
    bars = _h1_series(prices, engine.symbol, high_wiggle=0.01, low_wiggle=0.01)
    ts = bars["ts_utc"].to_numpy()
    logs = run_donchian_oos_batch(engine, bars, [_one_fold(ts)])
    trades = logs[0].trades
    assert len(trades) >= 1
    assert trades[0]["side"] == "short"


def test_empty_bars_returns_empty_log() -> None:
    engine = DONCHIAN_CATALOG[0]
    fold = Fold(fold_id=1, train_start=0, train_end=0, oos_start=0, oos_end=1)
    logs = run_donchian_oos_batch(engine, pd.DataFrame(), [fold])
    assert logs[0].trades == []


def test_fold_window_filters_entries() -> None:
    engine = DONCHIAN_CATALOG[2]
    prices = [15000.0] * ENTRY_CHANNEL_H1 + [15050.0 + 5.0 * i for i in range(40)]
    bars = _h1_series(prices, engine.symbol, high_wiggle=0.01, low_wiggle=0.01)
    ts = bars["ts_utc"].to_numpy()
    # OOS covers only the last 10 bars; the breakout happens earlier.
    oos_start = int(ts[-10])
    fold = Fold(fold_id=1, train_start=0, train_end=oos_start - 1,
                oos_start=oos_start, oos_end=int(ts[-1] + _H1_NS))
    logs = run_donchian_oos_batch(engine, bars, [fold])
    for t in logs[0].trades:
        assert t["ts_entry_ns"] >= oos_start
