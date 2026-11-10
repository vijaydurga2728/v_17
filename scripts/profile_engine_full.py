"""Profile 1 engine × all symbols × 7 folds using run_engine_oos_batch.

Per-fold timings printed to stdout. No cProfile overhead.

Usage:
    PYTHONPATH=src python scripts/profile_engine_full.py
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
    cfg = next(c for c in ENGINE_CATALOG if c.engine_id == "SB-LDN-CE")
    folds = generate_folds()
    cal = pd.DataFrame({
        "timestamp_utc": pd.array([], dtype="int64"),
        "currency": pd.array([], dtype=object),
        "impact": pd.array([], dtype=object),
    })

    print(f"[{time.strftime('%H:%M:%S')}] Profile: {cfg.engine_id} × {cfg.symbols} × {len(folds)} folds (batch)", flush=True)

    frames = []
    for symbol in cfg.symbols:
        t_load = time.time()
        sym_bars = read_bars(root=Path("data"), symbol=symbol, partition="dev", dev_only=True)
        print(f"  load {symbol}: {time.time()-t_load:.1f}s ({len(sym_bars):,} bars)", flush=True)
        frames.append(sym_bars)

    bars = pd.concat(frames, ignore_index=True)

    t0 = time.time()
    fold_logs = run_engine_oos_batch(config=cfg, bars=bars, calendar=cal, folds=folds)
    total = time.time() - t0

    for log in fold_logs:
        print(f"  fold {log.fold_id}: {len(log.trades)} trades", flush=True)

    total_trades = sum(len(l.trades) for l in fold_logs)
    print(f"\nTotal: {total:.1f}s  ({total/60:.2f}min)  {total_trades} trades across {len(folds)} folds", flush=True)


if __name__ == "__main__":
    main()
