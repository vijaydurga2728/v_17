import numpy as np
import pandas as pd

from v17.structure.atr import atr


def _hlc(n: int, hi: float = 1.1, lo: float = 1.0, cl: float = 1.05) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "high": np.full(n, hi),
            "low": np.full(n, lo),
            "close": np.full(n, cl),
        }
    )


def test_atr_length_and_nans() -> None:
    out = atr(_hlc(30), period=14)
    assert len(out) == 30
    assert out.iloc[:13].isna().all()
    assert not out.iloc[13:].isna().any()


def test_atr_constant_range() -> None:
    out = atr(_hlc(30, hi=1.10, lo=1.00, cl=1.05), period=14)
    assert np.isclose(out.iloc[-1], 0.10)


def test_atr_rising_range() -> None:
    # expand HL spread over time: TR grows, ATR must rise
    i = np.arange(30, dtype=float)
    df = pd.DataFrame(
        {
            "high": 1.05 + 0.05 + i * 0.01,
            "low": 1.05 - 0.05 - i * 0.01,
            "close": np.full(30, 1.05),
        }
    )
    out = atr(df, period=14)
    assert out.iloc[-1] > out.iloc[14]
