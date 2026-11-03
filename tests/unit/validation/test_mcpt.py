from __future__ import annotations

import numpy as np
import pandas as pd

from v17.validation.mcpt import permute_bars


def _sample_bars() -> pd.DataFrame:
    n = 100
    ts = pd.date_range("2024-01-01 00:00", periods=n, freq="1min", tz="UTC")
    base = 1.1000 + np.cumsum(np.random.normal(0, 0.0001, n))
    opens = base
    closes = base + np.random.normal(0, 0.00005, n)
    highs = np.maximum(opens, closes) + np.abs(np.random.normal(0, 0.00005, n))
    lows = np.minimum(opens, closes) - np.abs(np.random.normal(0, 0.00005, n))
    return pd.DataFrame(
        {
            "ts": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.ones(n, dtype=np.int64),
            "spread_pips": np.full(n, 0.3),
        }
    )


def test_permute_bars_preserves_length_and_columns() -> None:
    bars = _sample_bars()
    perm = permute_bars(bars, seed=42)
    assert len(perm) == len(bars)
    assert list(perm.columns) == list(bars.columns)


def test_permute_bars_preserves_start_bar() -> None:
    bars = _sample_bars()
    perm = permute_bars(bars, seed=42)
    assert np.isclose(perm["open"].iloc[0], bars["open"].iloc[0])
    assert np.isclose(perm["high"].iloc[0], bars["high"].iloc[0])
    assert np.isclose(perm["low"].iloc[0], bars["low"].iloc[0])
    assert np.isclose(perm["close"].iloc[0], bars["close"].iloc[0])


def test_permute_bars_maintains_ohlc_integrity() -> None:
    bars = _sample_bars()
    perm = permute_bars(bars, seed=123)
    assert (perm["high"] >= perm["open"]).all()
    assert (perm["high"] >= perm["close"]).all()
    assert (perm["low"] <= perm["open"]).all()
    assert (perm["low"] <= perm["close"]).all()


def test_permute_bars_is_deterministic_with_seed() -> None:
    bars = _sample_bars()
    perm1 = permute_bars(bars, seed=99)
    perm2 = permute_bars(bars, seed=99)
    pd.testing.assert_frame_equal(perm1, perm2)


def test_permute_bars_changes_price_path() -> None:
    bars = _sample_bars()
    perm = permute_bars(bars, seed=77)
    # The intermediate price trajectory changes while preserving total return
    mid = len(bars) // 2
    assert not np.isclose(perm["close"].iloc[mid], bars["close"].iloc[mid])
    # Total net return is preserved (sum of permutations is invariant)
    assert np.isclose(perm["close"].iloc[-1], bars["close"].iloc[-1])
