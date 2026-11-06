"""Pilot timing: 1 engine × 1 symbol × 1 fold (SB-NYAM-CE × EURUSD × 2018).

Measures wall-clock of `run_engine_oos` end-to-end to decide whether full
dev MCPT is feasible as-is or needs optimization.

Usage:
    python scripts/pilot_engine_runner.py
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from v17.backtest.engine_runner import run_engine_oos
from v17.backtest.walkforward import generate_folds
from v17.setups.sb_engines import ENGINE_CATALOG
from v17.data.parquet_store import read_bars


def main() -> None:
    cfg = next(c for c in ENGINE_CATALOG if c.engine_id == "SB-NYAM-CE")
    fold = generate_folds()[0]  # OOS 2018

    print(f"[{time.strftime('%H:%M:%S')}] Pilot: {cfg.engine_id} × EURUSD × fold {fold.fold_id}")
    print(f"  OOS: {pd.Timestamp(fold.oos_start, tz='UTC')} .. {pd.Timestamp(fold.oos_end, tz='UTC')}")

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
    log = run_engine_oos(config=cfg, bars=bars, calendar=cal, fold=fold)
    t_run = time.time() - t1

    print(f"  Engine ran in {t_run:.1f}s ({t_run/60:.1f}min)")
    print(f"  Trades fired: {len(log.trades)}")
    if log.trades:
        print("  First 3 trades:")
        for t in log.trades[:3]:
            print(f"    {pd.Timestamp(t.ts_entry_ns, tz='UTC')} {t.side} entry={t.entry_price:.5f} sl={t.sl_price:.5f} tp={t.tp_price:.5f} R={t.r_multiple:.2f}")

    # Project full gate wall-clock
    # Single engine × 1 symbol × 1 fold = t_run
    # Full gate: 6 engines × ~2 symbols avg × 7 folds = 84 units
    # SB-LDN: 2 symbols × 7 = 14 per engine × 2 engines = 28
    # SB-NYAM: 3 symbols × 7 = 21 per engine × 2 engines = 42
    # SB-NYPM: 1 symbol × 7 = 7 per engine × 2 engines = 14
    # Total engine-symbol-fold units = 28 + 42 + 14 = 84
    projected = 84 * t_run
    print(f"  Projected full gate wall-clock: {projected:.0f}s = {projected/60:.1f}min = {projected/3600:.2f}h")


if __name__ == "__main__":
    main()
