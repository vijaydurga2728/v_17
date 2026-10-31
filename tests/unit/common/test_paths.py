from pathlib import Path

from v17.common.paths import parquet_file
from v17.common.types import TF, Symbol


def test_parquet_file_shape(tmp_path: Path) -> None:
    p = parquet_file(tmp_path, Symbol("EURUSD"), TF.M1, 2024)
    assert p == tmp_path / "EURUSD" / "1m" / "year=2024" / "part-00.parquet"
