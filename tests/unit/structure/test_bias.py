from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from v17.common.types import Bias
from v17.structure.bias import compute_bias


def _bars_1d(closes: list[float], start: datetime) -> pd.DataFrame:
    rows = []
    for i, c in enumerate(closes):
        ts = start + timedelta(days=i)
        rows.append({"ts": ts, "open": c, "high": c + 0.001, "low": c - 0.001, "close": c, "volume": 1, "spread_pips": 0.0})
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def _bars_4h(n: int, start: str) -> pd.DataFrame:
    """Build n 4h bars with drift and sine oscillation to create swings."""
    ts = pd.date_range(start, periods=n, freq="4h", tz="UTC")
    base = 1.10 + np.linspace(0, 0.01, n) + np.sin(np.arange(n) / 7) * 0.001
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


class TestBiasAtSwingLength3:
    def test_short_history_produces_bias_not_none(self) -> None:
        # 60 days of 1d bars (all >=20 for EMA) + 240 4h bars with drift+sine
        # swing_length=3 detects more swings than swing_length=10
        start_dt = datetime(2024, 1, 1, tzinfo=UTC)
        df_1d = _bars_1d([1.10 + i * 0.001 for i in range(60)], start_dt)
        df_4h = _bars_4h(240, "2024-01-01")
        bias = compute_bias(df_1d, df_4h)
        # With swing_length=3 on clean oscillating 4h data, we must detect ≥1 swing.
        # The last swing will either align or not with daily bias, but either way
        # it should not all be NONE due to missing swings.
        assert bias != Bias.NONE
