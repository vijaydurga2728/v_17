"""Cycle 6 CLI entrypoint."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import typer

from v17.data.c6_calendar import build_calendar_index
from v17.data.c6_pipeline import build_m5_paired, ingest_m1_paired
from v17.validation.c6_gates import (
    compute_metrics, evaluate_dev_gates, evaluate_holdout_gates,
)

app = typer.Typer(name="c6", help="Cycle 6 SPX-led intraday FX")


@app.command("ingest-m1")
def ingest_m1_cmd(
    bid_csv: Path = typer.Option(...),
    ask_csv: Path = typer.Option(...),
    symbol: str = typer.Option(...),
    out_root: Path = typer.Option(...),
):
    n = ingest_m1_paired(bid_csv, ask_csv, symbol, out_root)
    typer.echo(f"wrote {n} rows")


@app.command("build-m5")
def build_m5_cmd(
    m1_root: Path = typer.Option(...),
    m5_root: Path = typer.Option(...),
    symbol: str = typer.Option(...),
    year: int = typer.Option(...),
):
    n = build_m5_paired(m1_root, m5_root, symbol, year)
    typer.echo(f"wrote {n} m5 bars")


@app.command("build-calendar")
def build_calendar_cmd(
    ff_dir: Path = typer.Option(...),
    out: Path = typer.Option(...),
):
    n = build_calendar_index(ff_dir, out, ("USD", "AUD", "JPY"))
    typer.echo(f"indexed {n} events")


@app.command("grid")
def grid_cmd(
    dev_start: str = typer.Option(...),
    dev_end: str = typer.Option(...),
    out_csv: Path = typer.Option(...),
):
    typer.echo(f"grid run for {dev_start}..{dev_end} -> {out_csv}")  # full wiring in Task 17


@app.command("dev-report")
def dev_report_cmd(
    grid_csv: Path = typer.Option(..., help="Grid search CSV"),
    trade_log: Path = typer.Option(..., help="Trade log CSV"),
    mcpt_json: Path = typer.Option(..., help="MCPT results JSON"),
    paired_json: Path = typer.Option(..., help="Paired alpha results JSON"),
    out_md: Path = typer.Option(..., help="Output markdown path"),
):
    grid = pd.read_csv(grid_csv).sort_values("sharpe", ascending=False).reset_index(drop=True)
    best = grid.iloc[0].to_dict()
    tl = pd.read_csv(trade_log)
    ec = pd.DataFrame({"ts_utc": tl["entry_ts_ns"], "equity": 10_000})  # placeholder
    m = compute_metrics(tl, ec)
    mcpt = json.loads(mcpt_json.read_text())
    paired = json.loads(paired_json.read_text())
    gates = evaluate_dev_gates(m, mcpt["p_sharpe"], paired["A1"], paired["A2"], paired["A3"])

    lines = [
        "# Cycle 6 — Dev Gate Report",
        "",
        f"**Best config:** K={best['K']} slope_window={best['slope_window']} C={best['C']}",
        f"- sharpe={best['sharpe']:.3f}, pf={best['pf']:.3f}, trades={int(best['trade_count'])}",
        "",
        "## Gates",
        "",
        "| Gate | Observed | Required | Pass |",
        "|------|----------|----------|------|",
        f"| D1 Sharpe | {m['sharpe']:.3f} | >= 1.0 | {gates['D1']} |",
        f"| D2 MCPT p | {mcpt['p_sharpe']:.4f} | <= 0.05 | {gates['D2']} |",
        f"| D3 PF | {m['pf']:.3f} | >= 1.25 | {gates['D3']} |",
        f"| D4 max daily loss | {m['max_daily_loss_pct']:.3%} | >= -3.0% | {gates['D4']} |",
        f"| D5 max consec losing days | {m['max_consec_losing_days']} | <= 5 | {gates['D5']} |",
        f"| D6 trade count | {m['trade_count']} | >= 800 | {gates['D6']} |",
        f"| A1 vs random | p={paired['A1']:.4f} | <= 0.05 | {gates['A1']} |",
        f"| A2 vs regime-only | p={paired['A2']:.4f} | <= 0.10 | {gates['A2']} |",
        f"| A3 vs micro-only | p={paired['A3']:.4f} | <= 0.10 | {gates['A3']} |",
        "",
        f"**ALL GATES PASS: {gates['all_pass']}**",
        "",
        "## Sign-off",
        "- [ ] User approves parameters lock",
        "- [ ] Parameters frozen for holdout phase",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    typer.echo(str(out_md))
