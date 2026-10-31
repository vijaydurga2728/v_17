from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from v17.cli import app


@pytest.mark.skipif(
    not Path("data/parquet/EURUSD/1m/year=2024").exists(),
    reason="requires EURUSD 2024 parquet bars (run `v17 ingest` first)",
)
class TestJune2024EurusdBacktestRuns:
    """Smoke test: strict-ICT backtest runs clean and emits a run_id.

    Under canonical ICT (post-M11 peel-revert), June 2024 EURUSD may produce
    0 trades. Zero trades is a legitimate outcome of the strategy, not a
    failure of the backtest harness. This test asserts the backtest
    produces a valid run artifact; it does NOT assert trades > 0.
    """

    def test_backtest_produces_run_artifact(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "backtest",
                "--symbol",
                "EURUSD",
                "--from",
                "2024-06-01",
                "--to",
                "2024-06-30",
                "--seed",
                "42",
            ],
        )
        assert result.exit_code == 0, result.output
        token = next(t for t in result.output.split() if t.startswith("run_id="))
        run_id = token.split("=", 1)[1]
        metrics_path = Path("runs") / run_id / "metrics.json"
        assert metrics_path.exists()
        metrics = json.loads(metrics_path.read_text())
        # Only shape assertions; strategy edge is tested by walkforward + M6, not here.
        assert "trades" in metrics
        assert "pf" in metrics
        assert "max_dd_pct" in metrics
