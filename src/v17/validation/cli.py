from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import typer

from v17.common.dtos import BacktestConfig, RunReport
from v17.common.types import RunId, Symbol
from v17.config import get_settings
from v17.validation.evaluate import evaluate
from v17.validation.gate import GateWriter


def validate(run: str = typer.Option(..., "--run")) -> None:
    s = get_settings()
    run_dir = s.project_root / "runs" / run
    if not run_dir.exists():
        raise typer.BadParameter(f"no run dir {run_dir}")
    metrics = json.loads((run_dir / "metrics.json").read_text())
    mc_path = run_dir / "montecarlo.json"
    mc = json.loads(mc_path.read_text()) if mc_path.exists() else {}
    wf_path = run_dir / "walkforward.json"
    wf = json.loads(wf_path.read_text()) if wf_path.exists() else {}

    cfg = BacktestConfig(
        symbol=Symbol("EURUSD"),
        start=datetime(2015, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 1, tzinfo=UTC),
    )
    report = RunReport(
        run_id=RunId(run),
        config=cfg,
        trades=int(metrics.get("trades", 0)),
        winrate=float(metrics.get("winrate", 0.0)),
        pf=float(metrics.get("pf", 0.0)),
        sharpe=float(metrics.get("sharpe", 0.0)),
        max_dd_pct=float(metrics.get("max_dd_pct", 0.0)),
        net_pnl=Decimal(str(metrics.get("net_pnl", 0))),
        oos_trades=int(metrics.get("oos_trades", metrics.get("trades", 0))),
        oos_pf=float(metrics.get("oos_pf", metrics.get("pf", 0.0))),
        oos_sharpe=float(metrics.get("oos_sharpe", metrics.get("sharpe", 0.0))),
        oos_max_dd_pct=float(metrics.get("oos_max_dd_pct", metrics.get("max_dd_pct", 0.0))),
        walkforward_folds_passed=int(wf.get("folds_passed", 0)),
        mc_p5_pf=float(mc.get("p5_pf", 0.0)),
        mc_p95_max_dd_pct=float(mc.get("p95_max_dd_pct", 0.0)),
    )
    ok, reasons = evaluate(report)
    gate = GateWriter(s.state_root)
    if ok:
        p = gate.write_sentinel(report)
        typer.echo(f"GATE PASSED -> {p}")
        raise typer.Exit(0)
    gate.revoke()
    typer.echo("GATE FAILED. Reasons:")
    for r in reasons:
        typer.echo(f"  - {r}")
    raise typer.Exit(1)
