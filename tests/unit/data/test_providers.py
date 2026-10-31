from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from v17.common.types import TF, Symbol
from v17.data.parquet_store import write_1m
from v17.data.providers import ParquetBarProvider


def _seed(tmp_path: Path) -> None:
    ts = pd.date_range("2024-06-01", periods=120, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "ts": ts,
            "open": np.linspace(1.0, 1.012, 120),
            "high": np.linspace(1.001, 1.013, 120),
            "low": np.linspace(0.999, 1.011, 120),
            "close": np.linspace(1.0005, 1.0125, 120),
            "volume": np.ones(120, dtype="int64"),
            "spread_pips": np.full(120, 0.8),
        }
    )
    write_1m(df, Symbol("EURUSD"), tmp_path)


def test_bars_1m_count(tmp_path: Path) -> None:
    _seed(tmp_path)
    p = ParquetBarProvider(tmp_path)
    bars = list(
        p.bars(
            Symbol("EURUSD"),
            TF.M1,
            datetime(2024, 6, 1, 0, 0, tzinfo=UTC),
            datetime(2024, 6, 1, 0, 10, tzinfo=UTC),
        )
    )
    assert len(bars) == 11
    assert bars[0].tf == TF.M1


def test_bars_15m_count(tmp_path: Path) -> None:
    _seed(tmp_path)
    p = ParquetBarProvider(tmp_path)
    bars = list(
        p.bars(
            Symbol("EURUSD"),
            TF.M15,
            datetime(2024, 6, 1, 0, 0, tzinfo=UTC),
            datetime(2024, 6, 1, 2, 0, tzinfo=UTC),
        )
    )
    assert len(bars) == 8
    assert bars[0].tf == TF.M15
