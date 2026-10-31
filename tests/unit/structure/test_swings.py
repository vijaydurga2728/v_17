import numpy as np
import pandas as pd

from v17.common.types import TF
from v17.structure.swings import detect_swings


def _uptrend(n: int = 120) -> pd.DataFrame:
    ts = pd.date_range("2024-06-01", periods=n, freq="15min", tz="UTC")
    base = 1.10 + np.linspace(0, 0.02, n) + np.sin(np.arange(n) / 5) * 0.001
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


def test_detect_swings_returns_dtos() -> None:
    out = detect_swings(_uptrend(120), tf=TF.M15, swing_length=10)
    assert all(s.kind in {"bos", "choch"} for s in out)
    assert all(s.tf == TF.M15 for s in out)
