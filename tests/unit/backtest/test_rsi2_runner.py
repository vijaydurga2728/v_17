"""RSI(2) mean-reversion runner tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.backtest.rsi2_runner import run_rsi2_oos_batch, _rsi_wilder
from v17.backtest.walkforward import Fold
from v17.setups.rsi2_engines import RSI2_CATALOG


_H1_NS = 3_600_000_000_000


def _h1_series(prices: list[float], symbol: str, high_wiggle: float = 0.0001, low_wiggle: float = 0.0001) -> pd.DataFrame:
    n = len(prices)
    base = pd.Timestamp("2020-01-01", tz="UTC").value
    ts = base + np.arange(n, dtype=np.int64) * _H1_NS
    mids = np.array(prices)
    half_spread = 0.00005
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


def test_rsi_wilder_rising_series_hits_100():
    close = np.linspace(1.0, 2.0, 50)
    rsi = _rsi_wilder(close, 2)
    assert rsi[-1] > 99.0


def test_rsi_wilder_falling_series_hits_0():
    close = np.linspace(2.0, 1.0, 50)
    rsi = _rsi_wilder(close, 2)
    assert rsi[-1] < 1.0


def test_long_entry_on_rsi_below_10():
    engine = RSI2_CATALOG[0]  # EURUSD
    # Build sharp drop then rebound to trigger RSI(2) < 10 then > 50.
    down = [1.1000 - 0.0010 * i for i in range(30)]
    up = [1.1000 - 0.0010 * 29 + 0.0005 * (i + 1) for i in range(10)]
    bars = _h1_series(down + up, engine.symbol, high_wiggle=0.0005, low_wiggle=0.0005)
    ts = bars["ts_utc"].to_numpy()
    logs = run_rsi2_oos_batch(engine, bars, [_one_fold(ts)])
    trades = logs[0].trades
    assert len(trades) >= 1
    assert trades[0]["side"] == "long"


def test_short_entry_on_rsi_above_90():
    engine = RSI2_CATALOG[0]
    up = [1.1000 + 0.0010 * i for i in range(30)]
    down = [1.1000 + 0.0010 * 29 - 0.0005 * (i + 1) for i in range(10)]
    bars = _h1_series(up + down, engine.symbol, high_wiggle=0.0005, low_wiggle=0.0005)
    ts = bars["ts_utc"].to_numpy()
    logs = run_rsi2_oos_batch(engine, bars, [_one_fold(ts)])
    trades = logs[0].trades
    assert len(trades) >= 1
    assert trades[0]["side"] == "short"


def test_no_entry_on_flat_series():
    engine = RSI2_CATALOG[0]
    bars = _h1_series([1.1000] * 50, engine.symbol, high_wiggle=0.00005, low_wiggle=0.00005)
    ts = bars["ts_utc"].to_numpy()
    logs = run_rsi2_oos_batch(engine, bars, [_one_fold(ts)])
    assert logs[0].trades == []


def test_empty_bars_returns_empty_log():
    engine = RSI2_CATALOG[0]
    fold = Fold(fold_id=1, train_start=0, train_end=0, oos_start=0, oos_end=1)
    logs = run_rsi2_oos_batch(engine, pd.DataFrame(), [fold])
    assert logs[0].trades == []
