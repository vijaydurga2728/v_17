"""Optimization correctness test: new engine_runner must produce identical trades
to the pre-optimization baseline on SB-NYAM-CE × EURUSD × fold 1 OOS 2018."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from v17.backtest.engine_runner import run_engine_oos
from v17.backtest.walkforward import generate_folds
from v17.setups.sb_engines import ENGINE_CATALOG
from v17.data.parquet_store import read_bars

BASELINE_PATH = Path("tests/integration/_baseline_pilot_trades.json")


@pytest.mark.slow
def test_pilot_trades_match_baseline():
    if not BASELINE_PATH.exists():
        pytest.skip("baseline not committed yet")
    with open(BASELINE_PATH) as f:
        baseline = json.load(f)
    cfg = next(c for c in ENGINE_CATALOG if c.engine_id == "SB-NYAM-CE")
    fold = generate_folds()[0]
    bars = read_bars(root=Path("data"), symbol="EURUSD", partition="dev", dev_only=True)
    cal = pd.DataFrame({
        "timestamp_utc": pd.array([], dtype="int64"),
        "currency": pd.array([], dtype=object),
        "impact": pd.array([], dtype=object),
    })
    log = run_engine_oos(config=cfg, bars=bars, calendar=cal, fold=fold)
    assert len(log.trades) == len(baseline), (
        f"trade count {len(log.trades)} != baseline {len(baseline)}"
    )
    for actual, expected in zip(log.trades, baseline):
        assert actual.ts_entry_ns == expected["ts_entry_ns"], (
            f"ts mismatch: {actual.ts_entry_ns} != {expected['ts_entry_ns']}"
        )
        assert actual.side == expected["side"], (
            f"side mismatch: {actual.side} != {expected['side']}"
        )
        assert abs(actual.entry_price - expected["entry_price"]) < 1e-5, (
            f"entry mismatch: {actual.entry_price} vs {expected['entry_price']}"
        )
        assert abs(actual.sl_price - expected["sl_price"]) < 1e-5, (
            f"sl mismatch: {actual.sl_price} vs {expected['sl_price']}"
        )
        assert abs(actual.tp_price - expected["tp_price"]) < 1e-5, (
            f"tp mismatch: {actual.tp_price} vs {expected['tp_price']}"
        )
