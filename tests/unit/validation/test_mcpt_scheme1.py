import pandas as pd
import numpy as np
from v17.validation.mcpt import permute_signal_time
from v17.setups.sb_engines import ENGINE_CATALOG


def test_permutation_produces_same_count_different_timestamps():
    trades = pd.DataFrame({
        "ts_entry_ns": pd.date_range("2024-03-15 14:00", periods=10, freq="min", tz="UTC").astype("int64"),
        "side": ["LONG"] * 10,
        "symbol": ["EURUSD"] * 10,
    })
    bars = pd.DataFrame({
        "ts_utc": pd.date_range("2024-03-15 14:00", "2024-03-15 15:00", freq="min", tz="UTC").astype("int64"),
        "symbol": "EURUSD",
    })
    cfg = next(c for c in ENGINE_CATALOG if c.engine_id == "SB-NYAM-CE")
    permuted = permute_signal_time(trades, bars, config=cfg, seed=42)
    assert len(permuted) == len(trades)
    assert not permuted["ts_entry_ns"].equals(trades["ts_entry_ns"])


def test_permutation_deterministic_with_seed():
    trades = pd.DataFrame({
        "ts_entry_ns": pd.date_range("2024-03-15 14:00", periods=5, freq="min", tz="UTC").astype("int64"),
        "side": ["LONG"] * 5,
        "symbol": ["EURUSD"] * 5,
    })
    bars = pd.DataFrame({
        "ts_utc": pd.date_range("2024-03-15 14:00", "2024-03-15 15:00", freq="min", tz="UTC").astype("int64"),
        "symbol": "EURUSD",
    })
    cfg = next(c for c in ENGINE_CATALOG if c.engine_id == "SB-NYAM-CE")
    a = permute_signal_time(trades, bars, config=cfg, seed=42)
    b = permute_signal_time(trades, bars, config=cfg, seed=42)
    assert a["ts_entry_ns"].equals(b["ts_entry_ns"])


def test_permutation_none_config_passthrough():
    trades = pd.DataFrame({
        "ts_entry_ns": pd.date_range("2024-03-15 14:00", periods=5, freq="min", tz="UTC").astype("int64"),
        "side": ["LONG"] * 5,
        "symbol": ["EURUSD"] * 5,
    })
    bars = pd.DataFrame({
        "ts_utc": pd.array([], dtype="int64"),
        "symbol": pd.array([], dtype=object),
    })
    out = permute_signal_time(trades, bars, config=None, seed=1)
    assert out["ts_entry_ns"].equals(trades["ts_entry_ns"])
