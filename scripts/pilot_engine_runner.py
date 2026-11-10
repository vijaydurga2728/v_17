"""Pilot timing v3: 1 engine × 1 symbol × 7 folds using run_engine_oos_batch.

Demonstrates that batch preprocessing eliminates per-fold GC overhead.

Usage:
    PYTHONPATH=src python scripts/pilot_engine_runner.py
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from v17.backtest.engine_runner import run_engine_oos_batch
from v17.backtest.walkforward import generate_folds
from v17.setups.sb_engines import ENGINE_CATALOG
from v17.data.parquet_store import read_bars


def main() -> None:
    cfg = next(c for c in ENGINE_CATALOG if c.engine_id == "SB-NYAM-CE")
    folds = generate_folds()  # all 7 folds

    print(f"[{time.strftime('%H:%M:%S')}] Pilot v3: {cfg.engine_id} × EURUSD × {len(folds)} folds (batch)")

    t0 = time.time()
    bars = read_bars(root=Path("data"), symbol="EURUSD", partition="dev", dev_only=True)
    t_load = time.time() - t0
    print(f"  Loaded {len(bars):,} EURUSD dev bars in {t_load:.1f}s")

    cal = pd.DataFrame({
        "timestamp_utc": pd.array([], dtype="int64"),
        "currency": pd.array([], dtype=object),
        "impact": pd.array([], dtype=object),
    })

    t1 = time.time()
    fold_logs = run_engine_oos_batch(config=cfg, bars=bars, calendar=cal, folds=folds)
    t_batch = time.time() - t1

    total_trades = sum(len(log.trades) for log in fold_logs)
    print(f"  Batch ran in {t_batch:.1f}s ({t_batch/60:.2f}min) — {len(folds)} folds")
    print(f"  Total trades: {total_trades}")
    for log in fold_logs:
        print(f"    fold {log.fold_id}: {len(log.trades)} trades")

    print(f"\n  vs baseline: 16.6s single-fold (pre-batch)")
    print(f"  Speedup factor vs sequential: {16.6 * 7 / t_batch:.1f}x")


if __name__ == "__main__":
    main()
