from pathlib import Path

import pytest

from v17.common.errors import V17DataError
from v17.data.dukascopy_csv import EXPECTED_OHLCV, parse_header, validate_schema


def _write(path: Path, header: str, line: str = "") -> Path:
    path.write_text(header + ("\n" + line if line else ""), encoding="utf-8")
    return path


def test_parse_header_strips_quotes(tmp_path: Path) -> None:
    p = _write(tmp_path / "a.csv", '"Gmt time","Open","High","Low","Close","Volume"')
    assert parse_header(p) == ["Gmt time", *EXPECTED_OHLCV]


def test_validate_schema_rejects_bad_cols(tmp_path: Path) -> None:
    p = _write(tmp_path / "b.csv", "a,b,c")
    with pytest.raises(V17DataError):
        validate_schema(p)
