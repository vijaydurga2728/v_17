"""WF orchestrator — run all 6 engines × 7 folds and persist per-engine trade logs.

Task 8.0b (Phase B): parallel engines via ProcessPoolExecutor.
  - Each engine runs in its own process (CPU-bound, GIL-free).
  - Preprocessing (D1 bars, FVG cache, SpreadGuard) done once per symbol via
    run_engine_oos_batch.
  - Falls back to sequential execution if ProcessPoolExecutor is unavailable.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from v17.backtest.engine_runner import run_engine_oos_batch
from v17.backtest.walkforward import generate_folds
from v17.setups.sb_engines import ENGINE_CATALOG, SBEngineConfig


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame({
        "ts_utc": pd.array([], dtype="int64"),
        "symbol": pd.array([], dtype=object),
        "bid_o": pd.array([], dtype="float64"),
        "bid_h": pd.array([], dtype="float64"),
        "bid_l": pd.array([], dtype="float64"),
        "bid_c": pd.array([], dtype="float64"),
        "ask_o": pd.array([], dtype="float64"),
        "ask_h": pd.array([], dtype="float64"),
        "ask_l": pd.array([], dtype="float64"),
        "ask_c": pd.array([], dtype="float64"),
        "spread_mid": pd.array([], dtype="float64"),
    })


def _empty_calendar() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp_utc": pd.array([], dtype="int64"),
        "currency": pd.array([], dtype=object),
        "impact": pd.array([], dtype=object),
    })


def _load_bars_for_engine(engine: SBEngineConfig, data_root: Path, dry_run: bool) -> pd.DataFrame:
    """Load and concatenate bars for all symbols of one engine."""
    if dry_run:
        return _empty_bars()
    frames = []
    for symbol in engine.symbols:
        try:
            from v17.data.parquet_store import read_bars
            sym_bars = read_bars(root=data_root, symbol=symbol, partition="dev", dev_only=True)
            frames.append(sym_bars)
        except Exception:
            pass
    if not frames:
        return _empty_bars()
    return pd.concat(frames, ignore_index=True)


def _run_one_engine(
    engine: SBEngineConfig,
    data_root: Path,
    out_root: Path,
    calendar: pd.DataFrame,
    folds: list,
    dry_run: bool,
) -> None:
    """Worker: load bars, run batch engine, write per-engine trades.parquet."""
    bars = _load_bars_for_engine(engine, data_root, dry_run)
    fold_logs = run_engine_oos_batch(
        config=engine, bars=bars, calendar=calendar, folds=folds
    )

    all_trades: list[dict] = []
    for log in fold_logs:
        for t in log.trades:
            if isinstance(t, dict):
                # Phase C/D path: dict with pnl_r, pnl_cash, etc.
                rec = {
                    "engine_id": engine.engine_id,
                    "fold_id": log.fold_id,
                    "symbol": t.get("symbol"),
                    "side": t.get("side"),
                    "ts_entry_ns": t.get("ts_entry_ns"),
                    "entry_price": t.get("entry_price"),
                    "sl_price": t.get("sl_price"),
                    "tp_price": t.get("tp_price"),
                    "r_multiple": t.get("r_multiple"),
                    "fvg_top": t.get("fvg_top"),
                    "fvg_bottom": t.get("fvg_bottom"),
                    "exit_reason": t.get("exit_reason"),
                    "exit_price": t.get("exit_price"),
                    "pnl_r": t.get("pnl_r"),
                    "pnl_cash": t.get("pnl_cash"),
                }
            else:
                # Legacy SBSignal path (dry_run / legacy callers).
                rec = {
                    "engine_id": engine.engine_id,
                    "fold_id": log.fold_id,
                    "symbol": t.symbol,
                    "side": t.side,
                    "ts_entry_ns": t.ts_entry_ns,
                    "entry_price": t.entry_price,
                    "sl_price": t.sl_price,
                    "tp_price": t.tp_price,
                    "r_multiple": t.r_multiple,
                    "fvg_top": t.fvg_top,
                    "fvg_bottom": t.fvg_bottom,
                    "exit_reason": None,
                    "exit_price": None,
                    "pnl_r": None,
                    "pnl_cash": None,
                }
            all_trades.append(rec)

    out = Path(out_root) / "wf" / engine.engine_id / "trades.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(all_trades)
    if df.empty:
        df = pd.DataFrame({
            "engine_id": pd.array([], dtype=object),
            "fold_id": pd.array([], dtype="int64"),
            "symbol": pd.array([], dtype=object),
            "side": pd.array([], dtype=object),
            "ts_entry_ns": pd.array([], dtype="int64"),
            "entry_price": pd.array([], dtype="float64"),
            "sl_price": pd.array([], dtype="float64"),
            "tp_price": pd.array([], dtype="float64"),
            "r_multiple": pd.array([], dtype="float64"),
            "fvg_top": pd.array([], dtype="float64"),
            "fvg_bottom": pd.array([], dtype="float64"),
            "exit_reason": pd.array([], dtype=object),
            "exit_price": pd.array([], dtype="float64"),
            "pnl_r": pd.array([], dtype="float64"),
            "pnl_cash": pd.array([], dtype="float64"),
        })
    df.to_parquet(out, index=False)


def run_all_engines_all_folds(
    data_root: Path,
    out_root: Path,
    dry_run: bool = False,
    max_workers: int | None = None,
) -> None:
    """Run all 6 engines in parallel (ProcessPoolExecutor) or sequentially."""
    folds = generate_folds()
    if dry_run:
        calendar = _empty_calendar()
    else:
        cal_path = Path(data_root) / "calendar" / "economic_events.parquet"
        calendar = (
            pd.read_parquet(cal_path) if cal_path.exists() else _empty_calendar()
        )

    # Try parallel first; fall back to sequential if spawn fails.
    try:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        n_workers = max_workers or min(len(ENGINE_CATALOG), os.cpu_count() or 1)
        futures: dict = {}
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            for engine in ENGINE_CATALOG:
                fut = ex.submit(
                    _run_one_engine,
                    engine, Path(data_root), Path(out_root), calendar, folds, dry_run,
                )
                futures[fut] = engine.engine_id
            failures: list[tuple[str, Exception]] = []
            for fut in as_completed(futures):
                eid = futures[fut]
                try:
                    fut.result()
                    print(f"[orchestrator] DONE {eid}", flush=True)
                except Exception as exc:
                    print(f"[orchestrator] FAIL {eid}: {exc}", flush=True)
                    failures.append((eid, exc))
            if failures:
                msgs = "; ".join(f"{eid}: {exc}" for eid, exc in failures)
                raise RuntimeError(f"Workers failed: {msgs}")
    except RuntimeError:
        raise  # propagate worker failures
    except Exception:
        # Sequential fallback (e.g., spawn not available on this platform).
        for engine in ENGINE_CATALOG:
            _run_one_engine(
                engine, Path(data_root), Path(out_root), calendar, folds, dry_run
            )
