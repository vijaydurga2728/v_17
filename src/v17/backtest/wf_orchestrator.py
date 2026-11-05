"""WF orchestrator — run all 6 engines × 7 folds and persist per-engine trade logs."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from v17.backtest.engine_runner import run_engine_oos
from v17.backtest.walkforward import generate_folds
from v17.setups.sb_engines import ENGINE_CATALOG


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


def run_all_engines_all_folds(data_root: Path, out_root: Path, dry_run: bool = False) -> None:
    folds = generate_folds()
    if dry_run:
        calendar = _empty_calendar()
    else:
        cal_path = Path(data_root) / "calendar" / "economic_events.parquet"
        calendar = (
            pd.read_parquet(cal_path) if cal_path.exists() else _empty_calendar()
        )
    for engine in ENGINE_CATALOG:
        all_trades: list[dict] = []
        for symbol in engine.symbols:
            if dry_run:
                bars = _empty_bars()
            else:
                try:
                    from v17.data.parquet_store import read_bars
                    bars = read_bars(root=Path(data_root), symbol=symbol, partition="dev", dev_only=True)
                except Exception:
                    bars = _empty_bars()
            for fold in folds:
                log = run_engine_oos(
                    config=engine, bars=bars, calendar=calendar, fold=fold,
                )
                for t in log.trades:
                    rec = {
                        "engine_id": engine.engine_id,
                        "fold_id": fold.fold_id,
                        "symbol": t.symbol,
                        "side": t.side,
                        "ts_entry_ns": t.ts_entry_ns,
                        "entry_price": t.entry_price,
                        "sl_price": t.sl_price,
                        "tp_price": t.tp_price,
                        "r_multiple": t.r_multiple,
                        "fvg_top": t.fvg_top,
                        "fvg_bottom": t.fvg_bottom,
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
            })
        df.to_parquet(out, index=False)
