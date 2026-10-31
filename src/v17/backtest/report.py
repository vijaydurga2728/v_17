from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from v17.common.dtos import BacktestConfig, Trade
from v17.common.types import RunId


def run_id_from_cfg(cfg: BacktestConfig) -> RunId:
    raw = f"{cfg.symbol}:{cfg.start.isoformat()}:{cfg.end.isoformat()}:{cfg.seed}".encode()
    return RunId(hashlib.sha1(raw).hexdigest()[:16])


def _trade_rows(trades: list[Trade]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for t in trades:
        rows.append(
            {
                "ticket": int(t.ticket),
                "signal_id": str(t.signal_id),
                "symbol": str(t.symbol),
                "side": t.side.value,
                "size_lots": float(t.size_lots),
                "entry": float(t.entry),
                "sl": float(t.sl),
                "tp": float(t.tp),
                "opened_at": t.opened_at,
                "closed_at": t.closed_at,
                "close_price": float(t.close_price) if t.close_price is not None else None,
                "pnl": float(t.pnl) if t.pnl is not None else None,
                "reason": t.reason,
            }
        )
    return rows


def write_run(
    run_dir: Path,
    trades: list[Trade],
    equity: pd.DataFrame,
    metrics: dict[str, Any],
    wf: dict[str, Any] | None = None,
    mc: dict[str, Any] | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(_trade_rows(trades)).to_parquet(run_dir / "trades.parquet", compression="zstd")
    equity.to_parquet(run_dir / "equity.parquet", compression="zstd")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, default=_json_default, indent=2))
    if wf is not None:
        (run_dir / "walkforward.json").write_text(json.dumps(wf, default=_json_default, indent=2))
    if mc is not None:
        (run_dir / "montecarlo.json").write_text(json.dumps(mc, default=_json_default, indent=2))


def _json_default(x: object) -> object:
    if isinstance(x, Decimal):
        return float(x)
    iso = getattr(x, "isoformat", None)
    if callable(iso):
        result: object = iso()
        return result
    raise TypeError(f"not serializable: {type(x)}")
