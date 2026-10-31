from __future__ import annotations

from pathlib import Path

from v17.common.types import TF, Symbol


def parquet_file(parquet_root: Path, symbol: Symbol, tf: TF, year: int) -> Path:
    return parquet_root / symbol / tf.value / f"year={year}" / "part-00.parquet"
