from pathlib import Path

import pytest
from typer.testing import CliRunner

from v17.cli import app

runner = CliRunner()

_HEADER = '"Gmt time","Open","High","Low","Close","Volume"'
_BID = (
    "01.01.2024 00:00:00.000,1.1000,1.1002,1.0998,1.1001,10\n"
    "01.01.2024 00:01:00.000,1.1001,1.1003,1.1000,1.1002,12\n"
)
_ASK = (
    "01.01.2024 00:00:00.000,1.1001,1.1003,1.0999,1.1002,10\n"
    "01.01.2024 00:01:00.000,1.1002,1.1004,1.1001,1.1003,12\n"
)


def _seed(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "EURUSD_1 Min_Bid_2024.01.01_2024.01.01.csv").write_text(
        _HEADER + "\n" + _BID, encoding="utf-8"
    )
    (raw / "EURUSD_1 Min_Ask_2024.01.01_2024.01.01.csv").write_text(
        _HEADER + "\n" + _ASK, encoding="utf-8"
    )


def test_cli_ingest_eurusd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(tmp_path)
    monkeypatch.setenv("V17_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("V17_DUKASCOPY_CSV_DIR", str(tmp_path / "raw"))
    result = runner.invoke(app, ["ingest", "--symbol", "EURUSD"])
    assert result.exit_code == 0, result.stdout
    out = tmp_path / "data" / "parquet" / "EURUSD" / "1m" / "year=2024" / "part-00.parquet"
    assert out.exists()
