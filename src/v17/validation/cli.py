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

    cfg_path = run_dir / "config.json"
    if cfg_path.exists():
        cfg = BacktestConfig.model_validate_json(cfg_path.read_text())
    elif "config" in metrics:
        cfg = BacktestConfig.model_validate(metrics["config"])
    else:
        cfg = BacktestConfig(
            symbol=Symbol(metrics.get("symbol", "EURUSD")),
            start=datetime.fromisoformat(metrics.get("start", "2015-01-01T00:00:00+00:00")),
            end=datetime.fromisoformat(metrics.get("end", "2026-01-01T00:00:00+00:00")),
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
        oos_trades=int(metrics.get("oos_trades", 0)),
        oos_pf=float(metrics.get("oos_pf", 0.0)),
        oos_sharpe=float(metrics.get("oos_sharpe", 0.0)),
        oos_max_dd_pct=float(metrics.get("oos_max_dd_pct", 100.0)),
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


def mcpt_cmd(
    symbol: str = typer.Option(..., "--symbol"),
    start: str = typer.Option(..., "--from"),
    end: str = typer.Option(..., "--to"),
    runs: int = typer.Option(10, "--runs"),
    seed: int = typer.Option(42, "--seed"),
) -> None:
    sym = Symbol(symbol)
    s_dt = datetime.fromisoformat(start).replace(tzinfo=UTC)
    e_dt = datetime.fromisoformat(end).replace(tzinfo=UTC)

    from v17.backtest.cli import _load_bars_1m
    from v17.backtest.loop import EventLoop
    from v17.backtest.metrics import profit_factor
    from v17.backtest.precompute import precompute
    from v17.risk.engine import DefaultRiskEngine
    from v17.setups.judas_swing import JudasSwing
    from v17.setups.silver_bullet import SilverBullet
    from v17.validation.mcpt import permute_bars

    bars = _load_bars_1m(sym, s_dt, e_dt)
    if bars.empty:
        raise typer.BadParameter(f"no 1m bars for {symbol} in range")

    s = get_settings()
    calendar = None
    if s.news_filter_enabled:
        from v17.data.calendar.providers import FFCalendarProvider

        calendar = FFCalendarProvider(s.calendar_root)

    pre = precompute(bars, sym)
    loop = EventLoop(
        sym,
        [SilverBullet(), JudasSwing()],
        DefaultRiskEngine(),
        pre,
        calendar=calendar,
        news_window_min=s.news_window_min,
    )
    trades, _ = loop.run(s_dt, e_dt, Decimal("10000"))
    pnls = [t.pnl for t in trades if t.pnl is not None]
    real_pf = profit_factor(pnls) if pnls else 0.0

    typer.echo(f"Real {symbol}: trades={len(trades)} PF={real_pf:.2f}")

    better_count = 0
    perm_pfs: list[float] = []
    for i in range(runs):
        perm_seed = seed + i * 1000 + 1
        perm_bars = permute_bars(bars, seed=perm_seed)
        p_pre = precompute(perm_bars, sym)
        p_loop = EventLoop(
            sym,
            [SilverBullet(), JudasSwing()],
            DefaultRiskEngine(),
            p_pre,
            calendar=calendar,
            news_window_min=s.news_window_min,
        )
        p_trades, _ = p_loop.run(s_dt, e_dt, Decimal("10000"))
        p_pnls = [t.pnl for t in p_trades if t.pnl is not None]
        p_pf = profit_factor(p_pnls) if p_pnls else 0.0
        perm_pfs.append(p_pf)
        if p_pf >= real_pf:
            better_count += 1
        typer.echo(f"  Permutation {i+1}/{runs}: trades={len(p_trades)} PF={p_pf:.2f}")

    p_value = (1.0 + better_count) / (float(runs) + 1.0)
    passed = p_value < 0.05
    typer.echo(f"\nMCPT Summary for {symbol}:")
    typer.echo(f"  Real PF: {real_pf:.2f}")
    typer.echo(f"  Permutations >= Real: {better_count}/{runs}")
    typer.echo(f"  Empirical p-value: {p_value:.4f}")
    status_str = "PASSED (p < 0.05)" if passed else "FAILED (p >= 0.05, no edge over noise)"
    typer.echo(f"  Verdict: {status_str}")

