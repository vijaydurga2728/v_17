"""Time-Series Momentum runner tests (cycle 4B D1)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from v17.backtest.tsm_runner import run_tsm_oos_batch
from v17.backtest.walkforward import Fold
from v17.setups.tsm_constants import HOLD_D1, LOOKBACK_D1
from v17.setups.tsm_engines import TSM_CATALOG


_D1_NS = 86_400_000_000_000


def _synthetic_d1(n: int, drift: float, symbol: str, start_price: float = 15000.0) -> pd.DataFrame:
    base = pd.Timestamp("2015-01-01", tz="UTC").value
    ts = base + np.arange(n, dtype=np.int64) * _D1_NS
    mid = start_price + np.arange(n) * drift
    half_spread = 0.0005 * start_price
    return pd.DataFrame({
        "ts_utc": ts,
        "symbol": [symbol] * n,
        "bid_o": mid - half_spread,
        "bid_h": mid - half_spread + start_price * 0.001,
        "bid_l": mid - half_spread - start_price * 0.001,
        "bid_c": mid - half_spread,
        "ask_o": mid + half_spread,
        "ask_h": mid + half_spread + start_price * 0.001,
        "ask_l": mid + half_spread - start_price * 0.001,
        "ask_c": mid + half_spread,
        "bid_volume": np.full(n, 10.0),
        "ask_volume": np.full(n, 10.0),
        "spread_mid": np.full(n, 2 * half_spread),
    })


def _one_fold(ts: np.ndarray) -> Fold:
    return Fold(fold_id=1, train_start=0, train_end=int(ts[0] - 1),
                oos_start=int(ts[0]), oos_end=int(ts[-1] + _D1_NS))


def test_tsm_skips_before_first_rebalance() -> None:
    engine = TSM_CATALOG[2]
    bars = _synthetic_d1(100, drift=0.0, symbol=engine.symbol)
    ts = bars["ts_utc"].to_numpy()
    logs = run_tsm_oos_batch(engine, bars, [_one_fold(ts)])
    assert logs[0].trades == []


def test_tsm_emits_long_on_positive_drift() -> None:
    engine = TSM_CATALOG[2]
    n = LOOKBACK_D1 + HOLD_D1 * 2 + 10
    bars = _synthetic_d1(n, drift=5.0, symbol=engine.symbol)
    ts = bars["ts_utc"].to_numpy()
    logs = run_tsm_oos_batch(engine, bars, [_one_fold(ts)])
    trades = logs[0].trades
    assert len(trades) >= 1
    assert all(t["side"] == "long" for t in trades)


def test_tsm_emits_short_on_negative_drift() -> None:
    engine = TSM_CATALOG[2]
    n = LOOKBACK_D1 + HOLD_D1 * 2 + 10
    bars = _synthetic_d1(n, drift=-5.0, symbol=engine.symbol)
    ts = bars["ts_utc"].to_numpy()
    logs = run_tsm_oos_batch(engine, bars, [_one_fold(ts)])
    trades = logs[0].trades
    assert len(trades) >= 1
    assert all(t["side"] == "short" for t in trades)


def test_tsm_empty_bars_returns_empty_log() -> None:
    engine = TSM_CATALOG[0]
    fold = Fold(fold_id=1, train_start=0, train_end=0, oos_start=0, oos_end=1)
    logs = run_tsm_oos_batch(engine, pd.DataFrame(), [fold])
    assert logs[0].trades == []


def test_tsm_fold_window_filters_trades() -> None:
    engine = TSM_CATALOG[2]
    n = LOOKBACK_D1 + HOLD_D1 * 4 + 10
    bars = _synthetic_d1(n, drift=5.0, symbol=engine.symbol)
    ts = bars["ts_utc"].to_numpy()
    half_ts = int(ts[len(ts) // 2])
    fold = Fold(fold_id=1, train_start=0, train_end=half_ts - 1,
                oos_start=half_ts, oos_end=int(ts[-1] + _D1_NS))
    logs = run_tsm_oos_batch(engine, bars, [fold])
    for t in logs[0].trades:
        assert t["ts_entry_ns"] >= half_ts


def test_tsm_no_hard_target_only_sl_or_hold() -> None:
    engine = TSM_CATALOG[2]
    n = LOOKBACK_D1 + HOLD_D1 * 2 + 10
    bars = _synthetic_d1(n, drift=5.0, symbol=engine.symbol)
    ts = bars["ts_utc"].to_numpy()
    logs = run_tsm_oos_batch(engine, bars, [_one_fold(ts)])
    for t in logs[0].trades:
        assert t["exit_reason"] in ("SL", "HOLD_END", "FOLD_END")
        assert "tp" not in t  # cycle 4B: no hard target field
