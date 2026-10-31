from pathlib import Path

import pytest
from typer.testing import CliRunner

from v17.cli import app

runner = CliRunner()


@pytest.mark.integration
def test_backtest_q1_2024_eurusd() -> None:
    if not (Path("data/parquet") / "EURUSD").exists():
        pytest.skip("real data not ingested")
    # Use a 2-week slice; full-period runs are perf-tuned later.
    result = runner.invoke(
        app, ["backtest", "--symbol", "EURUSD", "--from", "2024-06-03", "--to", "2024-06-07"]
    )
    assert result.exit_code == 0, result.stdout
    # metrics file lives under runs/<run_id>/
    runs = Path("runs")
    assert runs.exists()
    assert any((p / "metrics.json").exists() for p in runs.iterdir() if p.is_dir())
