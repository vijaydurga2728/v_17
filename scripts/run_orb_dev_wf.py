"""ORB Reversal dev walk-forward runner.

Reads USATECHIDXUSD bars from V17_BARS_ROOT (defaults to the SB worktree so
no file copy is needed), runs ORB-NAS100 across 7 anchored folds covering
OOS years 2018-2024, writes trades.parquet + stats.json.

Usage:
  V17_BARS_ROOT=.worktrees/sb-6-engine-gate/data python scripts/run_orb_dev_wf.py
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.backtest.engine_runner import run_engine_oos_batch
from v17.backtest.walkforward import generate_folds
from v17.setups.orb_engines import ORB_CATALOG
from v17.data.parquet_store import read_bars
from v17.validation.stats import compute_stats


def _resolve_bars_root() -> Path:
    env = os.environ.get("V17_BARS_ROOT")
    if env:
        return Path(env)
    default = Path(__file__).resolve().parents[1] / ".worktrees" / "sb-6-engine-gate" / "data"
    return default


def main(trend_filter: bool = False) -> dict:
    bars_root = _resolve_bars_root()
    out_root = Path("out/orb/dev_filtered" if trend_filter else "out/orb/dev")
    out_root.mkdir(parents=True, exist_ok=True)

    folds = generate_folds()
    engine = ORB_CATALOG[0]  # ORB-NAS100 only this cycle

    print(f"[orb-dev-wf] bars_root={bars_root}", flush=True)
    bars = read_bars(root=bars_root, symbol=engine.symbol, partition="dev", dev_only=True)
    if bars.empty:
        raise SystemExit(f"[orb-dev-wf] no dev bars for {engine.symbol} at {bars_root}")
    print(f"[orb-dev-wf] loaded {len(bars):,} bars for {engine.symbol}", flush=True)

    calendar = pd.DataFrame(columns=["timestamp_utc", "currency", "impact"])  # news policy D deferred

    print(f"[orb-dev-wf] trend_filter={trend_filter}", flush=True)
    logs = run_engine_oos_batch(engine, bars, calendar, folds, trend_filter=trend_filter)

    all_trades: list[dict] = []
    for log in logs:
        for t in log.trades:
            rec = dict(t)
            rec["fold_id"] = log.fold_id
            all_trades.append(rec)

    out_dir = out_root / engine.engine_id
    out_dir.mkdir(parents=True, exist_ok=True)
    trades_df = pd.DataFrame(all_trades)
    trades_path = out_dir / "trades.parquet"
    trades_df.to_parquet(trades_path, index=False)
    print(f"[orb-dev-wf] wrote {trades_path} ({len(trades_df)} trades)", flush=True)

    stats_out: dict = {}
    if not trades_df.empty:
        s = compute_stats(
            trades_df["pnl_r"].to_numpy(),
            trades_df["ts_entry_ns"].to_numpy(),
        )
        stats_out = asdict(s) if hasattr(s, "__dataclass_fields__") else {
            "pf": s.pf, "trade_count": s.trade_count,
            "r2": getattr(s, "r2", None),
            "sharpe": getattr(s, "sharpe", None),
            "max_dd_pct": getattr(s, "max_dd_pct", None),
            "winrate": getattr(s, "winrate", None),
        }
        per_fold = trades_df.groupby("fold_id")["pnl_r"].sum().to_dict()
        stats_out["per_fold_pnl_r"] = {int(k): float(v) for k, v in per_fold.items()}
    else:
        stats_out = {"pf": None, "trade_count": 0, "per_fold_pnl_r": {}}

    stats_path = out_dir / "stats.json"
    stats_path.write_text(json.dumps(stats_out, indent=2))
    print(f"[orb-dev-wf] wrote {stats_path}", flush=True)
    print(f"[orb-dev-wf] stats: {stats_out}", flush=True)
    return {engine.engine_id: stats_out}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--trend-filter", action="store_true",
                    help="Apply pre-registered D1 EMA_20 ±3%% regime filter")
    args = ap.parse_args()
    main(trend_filter=args.trend_filter)
