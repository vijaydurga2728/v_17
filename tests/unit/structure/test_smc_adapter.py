import numpy as np
import pandas as pd

from v17.structure.smc_adapter import prepare_smc_df, smc_swing_highs_lows


def _ohlcv(n: int = 100) -> pd.DataFrame:
    ts = pd.date_range("2024-06-01", periods=n, freq="15min", tz="UTC")
    rng = np.random.default_rng(42)
    base = 1.10 + np.cumsum(rng.normal(0, 0.0005, n))
    return pd.DataFrame(
        {
            "ts": ts,
            "open": base,
            "high": base + 0.0005,
            "low": base - 0.0005,
            "close": base + rng.normal(0, 0.0001, n),
            "volume": np.ones(n, dtype="int64"),
            "spread_pips": np.full(n, 0.8),
        }
    )


def test_prepare_shape() -> None:
    df = prepare_smc_df(_ohlcv(50))
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.name == "ts"


def test_swing_highs_lows_returns_frame() -> None:
    df = prepare_smc_df(_ohlcv(100))
    out = smc_swing_highs_lows(df, swing_length=10)
    assert isinstance(out, pd.DataFrame)
    assert any("HighLow" in c or "Level" in c for c in out.columns)
