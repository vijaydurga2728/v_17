import numpy as np
import pandas as pd

from v17.common.types import TF
from v17.data.resample import resample


def _mk(n: int) -> pd.DataFrame:
    ts = pd.date_range("2024-06-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "ts": ts,
            "open": np.linspace(1.0, 1.0 + n * 0.0001, n),
            "high": np.linspace(1.0, 1.0 + n * 0.0001, n) + 0.0005,
            "low": np.linspace(1.0, 1.0 + n * 0.0001, n) - 0.0005,
            "close": np.linspace(1.0, 1.0 + n * 0.0001, n) + 0.0001,
            "volume": np.ones(n, dtype="int64"),
            "spread_pips": np.full(n, 0.8),
        }
    )


def test_15m_aggregation() -> None:
    df = _mk(30)
    out = resample(df, TF.M15)
    assert len(out) == 2
    assert out["open"].iloc[0] == df["open"].iloc[0]
    assert out["high"].iloc[0] == df["high"].iloc[0:15].max()
    assert out["low"].iloc[0] == df["low"].iloc[0:15].min()
    assert out["close"].iloc[0] == df["close"].iloc[14]
    assert out["volume"].iloc[0] == 15
    assert np.isclose(out["spread_pips"].iloc[0], 0.8)
