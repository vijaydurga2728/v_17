from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from v17.common.types import Symbol
from v17.data.parquet_store import read_1m, write_1m


def _mk(n: int, start: str = "2024-12-31 23:58:00") -> pd.DataFrame:
    ts = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "ts": ts,
            "open": np.linspace(1.1, 1.11, n),
            "high": np.linspace(1.11, 1.12, n),
            "low": np.linspace(1.09, 1.10, n),
            "close": np.linspace(1.10, 1.11, n),
            "volume": np.arange(n, dtype="int64"),
            "spread_pips": np.full(n, 0.8),
        }
    )


def test_write_partitions_by_year(tmp_path: Path) -> None:
    df = _mk(5)
    write_1m(df, Symbol("EURUSD"), tmp_path)
    assert (tmp_path / "EURUSD" / "1m" / "year=2024" / "part-00.parquet").exists()
    assert (tmp_path / "EURUSD" / "1m" / "year=2025" / "part-00.parquet").exists()


def test_read_range(tmp_path: Path) -> None:
    df = _mk(10, start="2024-06-01 00:00:00")
    write_1m(df, Symbol("EURUSD"), tmp_path)
    out = read_1m(
        Symbol("EURUSD"),
        datetime(2024, 6, 1, 0, 3, tzinfo=UTC),
        datetime(2024, 6, 1, 0, 6, tzinfo=UTC),
        tmp_path,
    )
    assert len(out) == 4
    assert out["ts"].is_monotonic_increasing
