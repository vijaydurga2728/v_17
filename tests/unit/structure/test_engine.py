import numpy as np
import pandas as pd
import pytest

from v17.common.errors import V17StructureError
from v17.common.types import TF, Symbol
from v17.structure.engine import DefaultStructureEngine


def _frame(n: int, start: str, freq: str, drift: float = 0.01) -> pd.DataFrame:
    ts = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    base = 1.10 + np.linspace(0, drift, n) + np.sin(np.arange(n) / 7) * 0.001
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


def test_engine_requires_all_tfs() -> None:
    eng = DefaultStructureEngine(symbol=Symbol("EURUSD"))
    with pytest.raises(V17StructureError):
        eng.analyze({TF.D1: _frame(50, "2024-04-01", "1D")})


def test_engine_returns_snapshot() -> None:
    bars = {
        TF.D1: _frame(60, "2024-04-01", "1D"),
        TF.H4: _frame(240, "2024-05-01", "4h"),
        TF.M15: _frame(500, "2024-06-01", "15min"),
        TF.M1: _frame(300, "2024-06-03 06:00", "1min"),
    }
    eng = DefaultStructureEngine(symbol=Symbol("EURUSD"))
    snap = eng.analyze(bars)
    assert snap.symbol == Symbol("EURUSD")
    assert snap.bias.value in {"bull", "bear", "none"}
