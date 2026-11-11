"""Donchian breakout runner tests (cycle 4B D1)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.backtest.donchian_runner import run_donchian_oos_batch
from v17.backtest.walkforward import Fold
from v17.setups.donchian_constants import ATR_PERIOD_D1, ENTRY_CHANNEL_D1
from v17.setups.donchian_engines import DONCHIAN_CATALOG


_D1_NS = 86_400_000_000_000


def _d1_series(prices: list[float], symbol: str, wiggle_frac: float = 0.001) -> pd.DataFrame:
    n = len(prices)
    base = pd.Timestamp("2015-01-01", tz="UTC").value
    ts = base + np.arange(n, dtype=np.int64) * _D1_NS
    mids = np.array(prices)
    half_spread = 0.0005 * mids[0]
    w = mids[0] * wiggle_frac
    return pd.DataFrame({
        "ts_utc": ts,
        "symbol": [symbol] * n,
        "bid_o": mids - half_spread,
        "bid_h": mids - half_spread + w,
        "bid_l": mids - half_spread - w,
        "bid_c": mids - half_spread,
        "ask_o": mids + half_spread,
        "ask_h": mids + half_spread + w,
        "ask_l": mids + half_spread - w,
        "ask_c": mids + half_spread,
        "bid_volume": np.full(n, 10.0),
        "ask_volume": np.full(n, 10.0),
        "spread_mid": np.full(n, 2 * half_spread),
    })


def _one_fold(ts: np.ndarray) -> Fold:
    return Fold(fold_id=1, train_start=0, train_end=int(ts[0] - 1),
                oos_start=int(ts[0]), oos_end=int(ts[-1] + _D1_NS))


def test_no_breakout_on_flat_series() -> None:
    engine = DONCHIAN_CATALOG[2]
    bars = _d1_series([15000.0] * 50, engine.symbol, wiggle_frac=0.0001)
    ts = bars["ts_utc"].to_numpy()
    logs = run_donchian_oos_batch(engine, bars, [_one_fold(ts)])
    assert logs[0].trades == []


def test_long_breakout_on_strong_rally() -> None:
    engine = DONCHIAN_CATALOG[2]
    # First ENTRY_CHANNEL_D1 + ATR_PERIOD_D1 bars flat, then strong rally.
    warmup = max(ENTRY_CHANNEL_D1, ATR_PERIOD_D1)
    prices = [15000.0] * warmup + [15050.0 + 20.0 * i for i in range(40)]
    bars = _d1_series(prices, engine.symbol, wiggle_frac=0.001)
    ts = bars["ts_utc"].to_numpy()
    logs = run_donchian_oos_batch(engine, bars, [_one_fold(ts)])
    trades = logs[0].trades
    assert len(trades) >= 1
    assert trades[0]["side"] == "long"
    assert trades[0]["exit_reason"] in ("SL", "TRAIL", "FOLD_END", "TIME")


def test_short_breakout_on_strong_drop() -> None:
    engine = DONCHIAN_CATALOG[2]
    warmup = max(ENTRY_CHANNEL_D1, ATR_PERIOD_D1)
    prices = [15000.0] * warmup + [14950.0 - 20.0 * i for i in range(40)]
    bars = _d1_series(prices, engine.symbol, wiggle_frac=0.001)
    ts = bars["ts_utc"].to_numpy()
    logs = run_donchian_oos_batch(engine, bars, [_one_fold(ts)])
    trades = logs[0].trades
    assert len(trades) >= 1
    assert trades[0]["side"] == "short"


def test_no_fixed_tp_field_in_trade_record() -> None:
    engine = DONCHIAN_CATALOG[2]
    warmup = max(ENTRY_CHANNEL_D1, ATR_PERIOD_D1)
    prices = [15000.0] * warmup + [15050.0 + 20.0 * i for i in range(40)]
    bars = _d1_series(prices, engine.symbol, wiggle_frac=0.001)
    ts = bars["ts_utc"].to_numpy()
    logs = run_donchian_oos_batch(engine, bars, [_one_fold(ts)])
    for t in logs[0].trades:
        assert "tp" not in t  # cycle 4B removes fixed TP


def test_empty_bars_returns_empty_log() -> None:
    engine = DONCHIAN_CATALOG[0]
    fold = Fold(fold_id=1, train_start=0, train_end=0, oos_start=0, oos_end=1)
    logs = run_donchian_oos_batch(engine, pd.DataFrame(), [fold])
    assert logs[0].trades == []


def test_fold_window_filters_entries() -> None:
    engine = DONCHIAN_CATALOG[2]
    warmup = max(ENTRY_CHANNEL_D1, ATR_PERIOD_D1)
    prices = [15000.0] * warmup + [15050.0 + 20.0 * i for i in range(40)]
    bars = _d1_series(prices, engine.symbol, wiggle_frac=0.001)
    ts = bars["ts_utc"].to_numpy()
    oos_start = int(ts[-10])
    fold = Fold(fold_id=1, train_start=0, train_end=oos_start - 1,
                oos_start=oos_start, oos_end=int(ts[-1] + _D1_NS))
    logs = run_donchian_oos_batch(engine, bars, [fold])
    for t in logs[0].trades:
        assert t["ts_entry_ns"] >= oos_start
