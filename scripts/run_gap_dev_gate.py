"""Gap-fade dev gate runner (cycle 3)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.backtest.gap_runner import run_gap_oos_batch
from v17.backtest.walkforward import generate_folds
from v17.data.parquet_store import read_bars
from v17.setups.gap_engines import GAP_CATALOG
from v17.setups.orb_constants import COST_SLIPPAGE_PTS
from v17.validation.secondary_gates import evaluate_secondary
from v17.validation.stats import compute_stats


def _bars_root() -> Path:
    env = os.environ.get("V17_BARS_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / ".worktrees" / "sb-6-engine-gate" / "data"


def _cost_stress_pf(engine, folds, bars) -> float:
    original = dict(COST_SLIPPAGE_PTS)
    try:
        for k, v in list(COST_SLIPPAGE_PTS.items()):
            COST_SLIPPAGE_PTS[k] = v * 2.0
        logs = run_gap_oos_batch(engine, bars, folds)
        pnl, ts = [], []
        for l in logs:
            for t in l.trades:
                pnl.append(t["pnl_r"]); ts.append(t["ts_entry_ns"])
        if not pnl:
            return 0.0
        s = compute_stats(np.array(pnl), np.array(ts))
        return float(s.pf)
    finally:
        COST_SLIPPAGE_PTS.clear()
        COST_SLIPPAGE_PTS.update(original)


def main() -> None:
    bars_root = _bars_root()
    engine = GAP_CATALOG[0]
    folds = generate_folds()

    trades_path = Path("out/gap/dev") / engine.engine_id / "trades.parquet"
    if not trades_path.exists():
        raise SystemExit(f"missing {trades_path}; run scripts/run_gap_dev_wf.py first")
    trades = pd.read_parquet(trades_path)
    print(f"[gap-dev-gate] {len(trades):,} trades", flush=True)

    print("[gap-dev-gate] 2x slippage stress...", flush=True)
    bars = read_bars(root=bars_root, symbol=engine.symbol, partition="dev", dev_only=True)
    stress_pf = _cost_stress_pf(engine, folds, bars)
    print(f"[gap-dev-gate] stress_pf={stress_pf:.3f}", flush=True)

    report = evaluate_secondary(trades, cost_stress_pf=stress_pf, min_trade_count=25)

    out = Path("docs/superpowers/plans/gap_dev_gate_report_2026-11-11.md")
    lines = [
        "# GAP-NAS100 Dev Gate Report — 2026-11-11",
        "",
        f"**Trades (dev, 7-fold OOS):** {report.details['trade_count']}",
        f"**PF:** {report.details['pf']:.4f}  (G1 >= 1.3: {'PASS' if report.G1_pass else 'FAIL'})",
        f"**Trade count:** {report.details['trade_count']}  (G2 >= 25: {'PASS' if report.G2_pass else 'FAIL'})",
        f"**All folds net-positive:** {'YES' if report.G3_pass else 'NO'}  (G3: {'PASS' if report.G3_pass else 'FAIL'})",
        f"**R^2:** {report.details['r2']:.4f}  (G4 >= 0.80: {'PASS' if report.G4_pass else 'FAIL'})",
        f"**Cost-stress PF (2x slippage):** {stress_pf:.3f}  (G5 >= 1.1: {'PASS' if report.G5_pass else 'FAIL'})",
        "",
        "### Per-fold pnl_r sum",
        "| Fold | PnL (R) |",
        "|---|---|",
        *[f"| {f} | {pnl:.3f} |" for f, pnl in sorted(report.details['per_fold'].items())],
        "",
        f"### Verdict: {'ADVANCE' if report.all_pass else 'SHELVE'}",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[gap-dev-gate] wrote {out}", flush=True)
    print(f"[gap-dev-gate] all_pass={report.all_pass}", flush=True)


if __name__ == "__main__":
    main()
