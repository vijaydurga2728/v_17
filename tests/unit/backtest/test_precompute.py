from datetime import UTC, datetime

import numpy as np
import pandas as pd

from v17.backtest.precompute import precompute, snapshot_at
from v17.common.types import Symbol


def _bars(n: int) -> pd.DataFrame:
    ts = pd.date_range("2024-04-01", periods=n, freq="1min", tz="UTC")
    base = 1.10 + np.linspace(0, 0.02, n) + np.sin(np.arange(n) / 23) * 0.0005
    return pd.DataFrame(
        {
            "ts": ts,
            "open": base,
            "high": base + 0.0005,
            "low": base - 0.0005,
            "close": base,
            "volume": np.ones(n, dtype="int64"),
            "spread_pips": np.full(n, 0.8),
        }
    )


def test_precompute_fills_tfs() -> None:
    pre = precompute(_bars(60 * 24 * 5), Symbol("EURUSD"))
    assert len(pre.bars_15m) > 0
    assert len(pre.bars_4h) > 0
    assert len(pre.bars_1d) > 0


def test_snapshot_time_filtered() -> None:
    pre = precompute(_bars(60 * 24 * 5), Symbol("EURUSD"))
    now = datetime(2024, 4, 2, tzinfo=UTC)
    snap = snapshot_at(pre, now)
    assert snap.at == now
    assert all(z.created_at <= now for z in snap.zones)
    assert all(s.at <= now for s in snap.swings)
    assert all(s.at <= now for s in snap.sweeps)
