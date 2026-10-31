import numpy as np
import pandas as pd

from v17.backtest.snapshot_cache import precompute_1m_choches, precompute_daily_ema20


def _bars_1d(n: int = 30) -> pd.DataFrame:
    ts = pd.date_range("2024-04-01", periods=n, freq="1D", tz="UTC")
    close = np.linspace(1.10, 1.12, n)
    return pd.DataFrame(
        {
            "ts": ts,
            "open": close,
            "high": close + 0.001,
            "low": close - 0.001,
            "close": close,
            "volume": np.ones(n, dtype="int64"),
            "spread_pips": np.full(n, 0.8),
        }
    )


def _bars_1m(n: int = 300) -> pd.DataFrame:
    ts = pd.date_range("2024-04-01", periods=n, freq="1min", tz="UTC")
    base = 1.10 + np.linspace(0, 0.005, n) + np.sin(np.arange(n) / 15) * 0.0005
    return pd.DataFrame(
        {
            "ts": ts,
            "open": base,
            "high": base + 0.0003,
            "low": base - 0.0003,
            "close": base,
            "volume": np.ones(n, dtype="int64"),
            "spread_pips": np.full(n, 0.3),
        }
    )


def test_daily_ema20_shape() -> None:
    ema = precompute_daily_ema20(_bars_1d(30))
    assert len(ema) == 30
    assert ema.name == "ema20"


def test_choches_only() -> None:
    choches = precompute_1m_choches(_bars_1m(300))
    assert all(s.kind == "choch" for s in choches)
