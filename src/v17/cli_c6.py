"""Cycle 6 CLI entrypoint."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import typer

from v17.backtest.c6_grid import run_grid
from v17.backtest.c6_runner import run_backtest
from v17.data.c6_calendar import build_calendar_index, load_calendar_index
from v17.data.c6_pipeline import build_m5_paired, ingest_m1_paired
from v17.validation.c6_gates import (
    compute_metrics, evaluate_dev_gates, evaluate_holdout_gates,
)
from v17.validation.c6_mcpt import scheme1_mcpt
from v17.validation.c6_paired_alpha import (
    null_micro_only, null_random_entries, null_regime_only, paired_alpha,
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


def _load_m5(root: Path, symbol: str, start_iso: str, end_iso: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start_iso, tz="UTC").value
    end_ts = pd.Timestamp(end_iso, tz="UTC").value
    frames = []
    for y_dir in sorted((root / symbol).glob("year=*")):
        frames.append(pq.read_table(y_dir / "part-00.parquet").to_pandas())
    df = pd.concat(frames, ignore_index=True)
    return df[(df["ts_utc"] >= start_ts) & (df["ts_utc"] <= end_ts)].reset_index(drop=True)


@app.command("grid")
def grid_cmd(
    spx_root: Path = typer.Option(...),
    fx_root: Path = typer.Option(...),
    calendar: Path = typer.Option(...),
    dev_start: str = typer.Option(...),
    dev_end: str = typer.Option(...),
    out_csv: Path = typer.Option(...),
):
    spx = _load_m5(spx_root, "USA500IDXUSD", dev_start, dev_end)
    aud = _load_m5(fx_root, "AUDUSD", dev_start, dev_end)
    jpy = _load_m5(fx_root, "USDJPY", dev_start, dev_end)
    cal = (
        load_calendar_index(calendar)
        if calendar.exists() and calendar.stat().st_size > 0
        else pd.DataFrame(columns=["ts_utc", "currency", "impact", "title"])
    )
    g = run_grid(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal,
                 spx["ts_utc"].min(), spx["ts_utc"].max(), 10_000.0)
    g.to_csv(out_csv, index=False)
    typer.echo(str(out_csv))


@app.command("mcpt-dev")
def mcpt_dev_cmd(
    spx_root: Path = typer.Option(...),
    fx_root: Path = typer.Option(...),
    calendar: Path = typer.Option(...),
    params_json: Path = typer.Option(...),
    dev_start: str = typer.Option(...),
    dev_end: str = typer.Option(...),
    n_permutations: int = typer.Option(...),
    out_json: Path = typer.Option(...),
):
    params = json.loads(params_json.read_text())
    spx = _load_m5(spx_root, "USA500IDXUSD", dev_start, dev_end)
    aud = _load_m5(fx_root, "AUDUSD", dev_start, dev_end)
    jpy = _load_m5(fx_root, "USDJPY", dev_start, dev_end)
    cal = (
        load_calendar_index(calendar)
        if calendar.exists()
        else pd.DataFrame(columns=["ts_utc", "currency", "impact", "title"])
    )
    tl, _ = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0,
                         spx["ts_utc"].min(), spx["ts_utc"].max())
    counts = tl.groupby(["symbol", "side"]).size().to_dict()

    def run_null(i):
        return null_random_entries(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params,
                                   10_000.0, counts, seed=42 + i)

    r = scheme1_mcpt(tl, run_null, n_permutations=n_permutations, seed=42)
    out_json.write_text(json.dumps(r), encoding="utf-8")
    typer.echo(str(out_json))


@app.command("paired-alpha-dev")
def paired_alpha_dev_cmd(
    spx_root: Path = typer.Option(...),
    fx_root: Path = typer.Option(...),
    calendar: Path = typer.Option(...),
    params_json: Path = typer.Option(...),
    dev_start: str = typer.Option(...),
    dev_end: str = typer.Option(...),
    out_json: Path = typer.Option(...),
):
    params = json.loads(params_json.read_text())
    spx = _load_m5(spx_root, "USA500IDXUSD", dev_start, dev_end)
    aud = _load_m5(fx_root, "AUDUSD", dev_start, dev_end)
    jpy = _load_m5(fx_root, "USDJPY", dev_start, dev_end)
    cal = (
        load_calendar_index(calendar)
        if calendar.exists()
        else pd.DataFrame(columns=["ts_utc", "currency", "impact", "title"])
    )
    tl_obs, _ = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0,
                              spx["ts_utc"].min(), spx["ts_utc"].max())
    counts = tl_obs.groupby(["symbol", "side"]).size().to_dict()
    tl_a = null_random_entries(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0, counts, seed=42)
    tl_b = null_regime_only(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0, seed=43)
    tl_c = null_micro_only(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0, seed=44)
    p_a = paired_alpha(tl_obs, tl_a, seed=100)
    p_b = paired_alpha(tl_obs, tl_b, seed=101)
    p_c = paired_alpha(tl_obs, tl_c, seed=102)
    out_json.write_text(json.dumps({"A1": p_a, "A2": p_b, "A3": p_c}), encoding="utf-8")
    typer.echo(str(out_json))


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


@app.command("backtest")
def backtest_cmd(
    spx_root: Path = typer.Option(...),
    fx_root: Path = typer.Option(...),
    calendar: Path = typer.Option(...),
    params_json: Path = typer.Option(...),
    start: str = typer.Option(...),
    end: str = typer.Option(...),
    out_trades: Path = typer.Option(...),
    out_equity: Path = typer.Option(...),
):
    params = json.loads(params_json.read_text())
    spx = _load_m5(spx_root, "USA500IDXUSD", start, end)
    aud = _load_m5(fx_root, "AUDUSD", start, end)
    jpy = _load_m5(fx_root, "USDJPY", start, end)
    cal = (
        load_calendar_index(calendar)
        if calendar.exists() and calendar.stat().st_size > 0
        else pd.DataFrame(columns=["ts_utc", "currency", "impact", "title"])
    )
    tl, ec = run_backtest(spx, {"AUDUSD": aud, "USDJPY": jpy}, cal, params, 10_000.0,
                          spx["ts_utc"].min(), spx["ts_utc"].max())
    tl.to_csv(out_trades, index=False)
    ec.to_csv(out_equity, index=False)
    typer.echo(f"{out_trades} {out_equity}")


@app.command("mcpt-holdout")
def mcpt_holdout_cmd(
    spx_root: Path = typer.Option(...),
    fx_root: Path = typer.Option(...),
    calendar: Path = typer.Option(...),
    params_json: Path = typer.Option(...),
    holdout_start: str = typer.Option(...),
    holdout_end: str = typer.Option(...),
    n_permutations: int = typer.Option(...),
    out_json: Path = typer.Option(...),
):
    # Same logic as mcpt-dev with different window.
    mcpt_dev_cmd(spx_root, fx_root, calendar, params_json,
                 holdout_start, holdout_end, n_permutations, out_json)


@app.command("holdout-report")
def holdout_report_cmd(
    dev_sharpe: float = typer.Option(...),
    trade_log: Path = typer.Option(...),
    mcpt_json: Path = typer.Option(...),
    out_md: Path = typer.Option(...),
):
    tl = pd.read_csv(trade_log)
    ec = pd.DataFrame({"ts_utc": tl["entry_ts_ns"], "equity": 10_000})
    m = compute_metrics(tl, ec)
    mcpt = json.loads(mcpt_json.read_text())
    g = evaluate_holdout_gates(m, dev_sharpe=dev_sharpe, mcpt_p=mcpt["p_sharpe"])
    lines = [
        "# Cycle 6 — Holdout Gate Report",
        "",
        f"dev_sharpe={dev_sharpe:.3f}",
        "",
        "| Gate | Observed | Required | Pass |",
        "|------|----------|----------|------|",
        f"| H1 Sharpe | {m['sharpe']:.3f} | >= {0.7 * dev_sharpe:.3f} | {g['H1']} |",
        f"| H2 MCPT p | {mcpt['p_sharpe']:.4f} | <= 0.10 | {g['H2']} |",
        f"| H3 PF | {m['pf']:.3f} | >= 1.15 | {g['H3']} |",
        f"| H4 max daily loss | {m['max_daily_loss_pct']:.3%} | >= -3.0% | {g['H4']} |",
        f"| H5 worst month | {m['worst_month_return']:.3%} | >= -5.0% | {g['H5']} |",
        "",
        f"**ALL HOLDOUT GATES PASS: {g['all_pass']}**",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    typer.echo(str(out_md))
