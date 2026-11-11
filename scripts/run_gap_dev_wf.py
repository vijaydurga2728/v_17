"""Gap-fade dev walk-forward runner (cycle 3)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.backtest.gap_runner import run_gap_oos_batch
from v17.backtest.walkforward import generate_folds
from v17.data.parquet_store import read_bars
from v17.setups.gap_engines import GAP_CATALOG
from v17.validation.stats import compute_stats


def _resolve_bars_root() -> Path:
    env = os.environ.get("V17_BARS_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / ".worktrees" / "sb-6-engine-gate" / "data"


def main() -> None:
    bars_root = _resolve_bars_root()
    out_root = Path("out/gap/dev")
    out_root.mkdir(parents=True, exist_ok=True)

    folds = generate_folds()
    engine = GAP_CATALOG[0]

    print(f"[gap-dev-wf] bars_root={bars_root}", flush=True)
    bars = read_bars(root=bars_root, symbol=engine.symbol, partition="dev", dev_only=True)
    if bars.empty:
        raise SystemExit(f"[gap-dev-wf] no dev bars for {engine.symbol}")
    print(f"[gap-dev-wf] loaded {len(bars):,} bars", flush=True)

    logs = run_gap_oos_batch(engine, bars, folds)

    all_trades: list[dict] = []
    for log in logs:
        for t in log.trades:
            all_trades.append(t)

    out_dir = out_root / engine.engine_id
    out_dir.mkdir(parents=True, exist_ok=True)
    trades_df = pd.DataFrame(all_trades)
    trades_path = out_dir / "trades.parquet"
    trades_df.to_parquet(trades_path, index=False)
    print(f"[gap-dev-wf] wrote {trades_path} ({len(trades_df)} trades)", flush=True)

    if not trades_df.empty:
        s = compute_stats(
            trades_df["pnl_r"].to_numpy(),
            trades_df["ts_entry_ns"].to_numpy(),
        )
        stats_out = asdict(s) if hasattr(s, "__dataclass_fields__") else {}
        per_fold = trades_df.groupby("fold_id")["pnl_r"].sum().to_dict()
        stats_out["per_fold_pnl_r"] = {int(k): float(v) for k, v in per_fold.items()}
    else:
        stats_out = {"trade_count": 0, "per_fold_pnl_r": {}}

    (out_dir / "stats.json").write_text(json.dumps(stats_out, indent=2))
    print(f"[gap-dev-wf] stats: {stats_out}", flush=True)


if __name__ == "__main__":
    main()
