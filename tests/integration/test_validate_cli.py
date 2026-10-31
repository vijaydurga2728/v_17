import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from v17.cli import app

runner = CliRunner()


_PASS_METRICS = {
    "trades": 500,
    "winrate": 0.55,
    "pf": 1.9,
    "sharpe": 2.1,
    "max_dd_pct": 5.0,
    "net_pnl": 12000.0,
    "oos_trades": 250,
    "oos_pf": 1.85,
    "oos_sharpe": 2.0,
    "oos_max_dd_pct": 5.5,
}

_FAIL_METRICS = {
    "trades": 50,
    "winrate": 0.30,
    "pf": 1.1,
    "sharpe": 0.8,
    "max_dd_pct": 12.0,
    "net_pnl": -2000.0,
    "oos_trades": 20,
    "oos_pf": 1.0,
    "oos_sharpe": 0.5,
    "oos_max_dd_pct": 14.0,
}


def _seed(tmp_path: Path, run_id: str, metrics: dict) -> None:
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "metrics.json").write_text(json.dumps(metrics))
    (run_dir / "montecarlo.json").write_text(json.dumps({"p5_pf": 1.4, "p95_max_dd_pct": 7.0}))
    (run_dir / "walkforward.json").write_text(json.dumps({"folds_passed": 6}))


def test_validate_pass_writes_sentinel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(tmp_path, "runA", _PASS_METRICS)
    monkeypatch.setenv("V17_PROJECT_ROOT", str(tmp_path))
    result = runner.invoke(app, ["validate", "--run", "runA"])
    assert result.exit_code == 0, result.stdout
    sentinel = tmp_path / "data" / "state" / "GATE_PASSED"
    assert sentinel.exists()
    payload = json.loads(sentinel.read_text())
    assert payload["run_id"] == "runA"


def test_validate_fail_revokes_and_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # pre-write a sentinel to verify revocation
    (tmp_path / "data" / "state").mkdir(parents=True)
    (tmp_path / "data" / "state" / "GATE_PASSED").write_text("stale")
    _seed(tmp_path, "runB", _FAIL_METRICS)
    monkeypatch.setenv("V17_PROJECT_ROOT", str(tmp_path))
    result = runner.invoke(app, ["validate", "--run", "runB"])
    assert result.exit_code == 1
    assert "GATE FAILED" in result.stdout
    assert not (tmp_path / "data" / "state" / "GATE_PASSED").exists()
