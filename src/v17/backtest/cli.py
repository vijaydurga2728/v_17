from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pandas as pd
import typer

from v17.backtest.loop import EventLoop
from v17.backtest.metrics import (
    daily_returns_from_equity,
    max_drawdown_pct,
    profit_factor,
    sharpe,
    winrate,
)
from v17.backtest.montecarlo import hybrid_mc
from v17.backtest.precompute import precompute
from v17.backtest.report import run_id_from_cfg, write_run
from v17.common.dtos import BacktestConfig
from v17.common.types import Symbol
from v17.config import get_settings
from v17.risk.engine import DefaultRiskEngine
from v17.setups.judas_swing import JudasSwing
from v17.setups.silver_bullet import SilverBullet


def _load_bars_1m(symbol: Symbol, start: datetime, end: datetime) -> pd.DataFrame:
    s = get_settings()
    s.ensure_dirs()
    from datetime import timedelta

    import numpy as np

    from v17.data.parquet_store import read_1m

    warmup_start = start - timedelta(days=60)
    df = read_1m(symbol, warmup_start, end, s.parquet_root)
    if df.empty:
        df = read_1m(symbol, start, end, s.parquet_root)
    if df.empty:
        return df
    df = df.copy()
    for col in ("open", "high", "low", "close", "spread_pips"):
        df[col] = df[col].astype(float)
    df["high"] = np.maximum(df["high"], np.maximum(df["open"], df["close"]))
    df["low"] = np.minimum(df["low"], np.minimum(df["open"], df["close"]))
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["volume"] = df["volume"].astype("int64")
    return df


def backtest(
    symbol: str = typer.Option(..., "--symbol"),
    start: str = typer.Option(..., "--from"),
    end: str = typer.Option(..., "--to"),
    seed: int = typer.Option(42, "--seed"),
) -> None:
    from datetime import UTC

    cfg = BacktestConfig(
        symbol=Symbol(symbol),
        start=datetime.fromisoformat(start).replace(tzinfo=UTC),
        end=datetime.fromisoformat(end).replace(tzinfo=UTC),
        seed=seed,
    )
    bars = _load_bars_1m(cfg.symbol, cfg.start, cfg.end)
    if bars.empty:
        raise typer.BadParameter(f"no 1m bars for {symbol} in range")
    pre = precompute(bars, cfg.symbol)
    s = get_settings()
    calendar = None
    if s.news_filter_enabled:
        from v17.data.calendar.providers import FFCalendarProvider

        calendar = FFCalendarProvider(s.calendar_root)
    loop = EventLoop(
        cfg.symbol,
        [SilverBullet(), JudasSwing()],
        DefaultRiskEngine(),
        pre,
        calendar=calendar,
        news_window_min=s.news_window_min,
    )
    trades, equity = loop.run(cfg.start, cfg.end, cfg.starting_equity)
    pnls = [t.pnl for t in trades if t.pnl is not None]
    equity_list = [cfg.starting_equity]
    for p in pnls:
        equity_list.append(equity_list[-1] + p)
    metrics = {
        "trades": len(trades),
        "winrate": winrate(pnls),
        "pf": profit_factor(pnls),
        "max_dd_pct": max(loop.max_floating_dd_pct, max_drawdown_pct(equity_list)),
        "sharpe": sharpe(daily_returns_from_equity(equity)),
        "net_pnl": float(sum(pnls, start=Decimal("0"))),
    }
    mc = (
        hybrid_mc(pnls, seed=cfg.seed, perm_runs=500, boot_runs=500, block=5)
        if len(pnls) >= 10
        else None
    )
    run_id = run_id_from_cfg(cfg)
    run_dir = get_settings().project_root / "runs" / run_id
    write_run(run_dir, trades, equity, metrics, None, dict(mc) if mc is not None else None)
    typer.echo(
        f"run_id={run_id} trades={metrics['trades']} pf={metrics['pf']:.2f} "
        f"dd={metrics['max_dd_pct']:.2f}% dir={run_dir}"
    )


def montecarlo_cmd(
    run: str = typer.Option(..., "--run"),
    runs: int = typer.Option(1000, "--runs"),
    seed: int = typer.Option(42, "--seed"),
) -> None:
    import json
    from decimal import Decimal

    s = get_settings()
    run_dir = s.project_root / "runs" / run
    if not run_dir.exists():
        raise typer.BadParameter(f"no run dir: {run_dir}")
    trades_path = run_dir / "trades.parquet"
    if not trades_path.exists():
        raise typer.BadParameter(f"no trades.parquet in {run_dir}")
    df = pd.read_parquet(trades_path)
    pnls = [Decimal(str(p)) for p in df["pnl"].dropna().tolist()]
    if len(pnls) < 10:
        raise typer.BadParameter(f"need ≥10 closed trades, got {len(pnls)}")
    perm = runs // 2
    boot = runs - perm
    mc = hybrid_mc(pnls, seed=seed, perm_runs=perm, boot_runs=boot, block=5)
    out = run_dir / "montecarlo.json"
    out.write_text(json.dumps(dict(mc)))
    typer.echo(
        f"p5_pf={mc['p5_pf']:.3f} p95_max_dd={mc['p95_max_dd_pct']:.2f}%  saved: {out}"
    )


def walkforward_cmd(
    symbol: str = typer.Option(..., "--symbol"),
    start: str = typer.Option(..., "--from"),
    end: str = typer.Option(..., "--to"),
    folds: int = typer.Option(12, "--folds"),
    seed: int = typer.Option(42, "--seed"),
) -> None:
    from datetime import UTC

    from v17.backtest.walkforward import anchored_folds

    cfg = BacktestConfig(
        symbol=Symbol(symbol),
        start=datetime.fromisoformat(start).replace(tzinfo=UTC),
        end=datetime.fromisoformat(end).replace(tzinfo=UTC),
        seed=seed,
    )
    bars = _load_bars_1m(cfg.symbol, cfg.start, cfg.end)
    pre = precompute(bars, cfg.symbol)
    loop = EventLoop(cfg.symbol, [SilverBullet(), JudasSwing()], DefaultRiskEngine(), pre)
    folds_cfg = anchored_folds(cfg.start, cfg.end, n_folds=folds, is_pct=0.6)
    agg: list[dict[str, float]] = []
    passed = 0
    for i, fold in enumerate(folds_cfg):
        trades, _equity = loop.run(fold["oos_start"], fold["oos_end"], cfg.starting_equity)
        pnls = [t.pnl for t in trades if t.pnl is not None]
        pf = profit_factor(pnls)
        agg.append(
            {
                "fold": i + 1,
                "oos_trades": len(trades),
                "oos_pf": pf,
                "oos_max_dd_pct": max_drawdown_pct(
                    [
                        cfg.starting_equity,
                        *[
                            cfg.starting_equity + Decimal(str(v))
                            for v in pd.Series(
                                [float(p) for p in pnls]
                            ).cumsum().tolist()
                        ],
                    ]
                )
                if pnls
                else 0.0,
            }
        )
        if pf >= 1.3:
            passed += 1
    typer.echo(
        f"folds={len(folds_cfg)} passed={passed} agg_sample={agg[:2]}"
    )
