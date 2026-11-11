"""RSI(2) runner tests (cycle 4B D1 Connors long-only)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.backtest.rsi2_runner import run_rsi2_oos_batch, _rsi_wilder, _sma
from v17.backtest.walkforward import Fold
from v17.setups.rsi2_engines import RSI2_CATALOG


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


def test_rsi_wilder_rising_series_hits_100():
    close = np.linspace(1.0, 2.0, 50)
    rsi = _rsi_wilder(close, 2)
    assert rsi[-1] > 99.0


def test_rsi_wilder_falling_series_hits_0():
    close = np.linspace(2.0, 1.0, 50)
    rsi = _rsi_wilder(close, 2)
    assert rsi[-1] < 1.0


def test_sma_simple_window():
    x = np.arange(10, dtype=float)
    m = _sma(x, 3)
    # last window = (7+8+9)/3 = 8
    assert abs(m[-1] - 8.0) < 1e-9
    assert np.isnan(m[0])


def test_long_entry_on_rsi_below_10_then_sma_exit():
    engine = RSI2_CATALOG[0]  # NAS100
    # Sharp drop (oversold) then rally (close > SMA(5) triggers exit).
    down = [15000.0 - 100.0 * i for i in range(20)]
    up = [down[-1] + 200.0 * (i + 1) for i in range(10)]
    bars = _d1_series(down + up, engine.symbol, wiggle_frac=0.002)
    ts = bars["ts_utc"].to_numpy()
    logs = run_rsi2_oos_batch(engine, bars, [_one_fold(ts)])
    trades = logs[0].trades
    assert len(trades) >= 1
    assert all(t["side"] == "long" for t in trades)
    assert any(t["exit_reason"] == "SMA_EXIT" for t in trades)


def test_no_short_entries_cycle_4b():
    engine = RSI2_CATALOG[0]
    # Strong rally -> RSI should go > 90 in old symmetric design. Here must produce zero trades.
    prices = [15000.0 + 100.0 * i for i in range(40)]
    bars = _d1_series(prices, engine.symbol, wiggle_frac=0.002)
    ts = bars["ts_utc"].to_numpy()
    logs = run_rsi2_oos_batch(engine, bars, [_one_fold(ts)])
    for t in logs[0].trades:
        assert t["side"] == "long"


def test_no_entry_on_flat_series():
    engine = RSI2_CATALOG[0]
    bars = _d1_series([15000.0] * 50, engine.symbol, wiggle_frac=0.0001)
    ts = bars["ts_utc"].to_numpy()
    logs = run_rsi2_oos_batch(engine, bars, [_one_fold(ts)])
    assert logs[0].trades == []


def test_empty_bars_returns_empty_log():
    engine = RSI2_CATALOG[0]
    fold = Fold(fold_id=1, train_start=0, train_end=0, oos_start=0, oos_end=1)
    logs = run_rsi2_oos_batch(engine, pd.DataFrame(), [fold])
    assert logs[0].trades == []


def test_no_stop_loss_field_in_trade():
    engine = RSI2_CATALOG[0]
    down = [15000.0 - 100.0 * i for i in range(20)]
    up = [down[-1] + 200.0 * (i + 1) for i in range(10)]
    bars = _d1_series(down + up, engine.symbol, wiggle_frac=0.002)
    ts = bars["ts_utc"].to_numpy()
    logs = run_rsi2_oos_batch(engine, bars, [_one_fold(ts)])
    for t in logs[0].trades:
        assert "sl" not in t
