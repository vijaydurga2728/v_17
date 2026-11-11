"""Run secondary gates G1-G5 on ORB-NAS100 dev trades.

Reads out/orb/dev/ORB-NAS100/trades.parquet. Computes cost-stress PF by
replaying with 2x slippage. Writes verdict report to
docs/superpowers/plans/orb_dev_gate_report_2026-11-11.md.
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
from v17.data.parquet_store import read_bars
from v17.setups.orb_constants import COST_SLIPPAGE_PTS
from v17.setups.orb_engines import ORB_CATALOG
from v17.validation.secondary_gates import evaluate_secondary
from v17.validation.stats import compute_stats


def _resolve_bars_root() -> Path:
    env = os.environ.get("V17_BARS_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / ".worktrees" / "sb-6-engine-gate" / "data"


def _cost_stress_pf(engine, folds, bars, calendar, trend_filter: bool = False) -> float:
    """Re-run with doubled slippage; return resulting PF."""
    original = dict(COST_SLIPPAGE_PTS)
    try:
        for k, v in list(COST_SLIPPAGE_PTS.items()):
            COST_SLIPPAGE_PTS[k] = v * 2.0
        logs = run_engine_oos_batch(engine, bars, calendar, folds, trend_filter=trend_filter)
        all_pnl = []
        all_ts = []
        for log in logs:
            for t in log.trades:
                all_pnl.append(t["pnl_r"])
                all_ts.append(t["ts_entry_ns"])
        if not all_pnl:
            return 0.0
        import numpy as np
        s = compute_stats(np.array(all_pnl), np.array(all_ts))
        return float(s.pf)
    finally:
        COST_SLIPPAGE_PTS.clear()
        COST_SLIPPAGE_PTS.update(original)


def main(trend_filter: bool = False) -> None:
    bars_root = _resolve_bars_root()
    engine = ORB_CATALOG[0]
    folds = generate_folds()

    dev_dir = Path("out/orb/dev_filtered" if trend_filter else "out/orb/dev")
    trades_path = dev_dir / engine.engine_id / "trades.parquet"
    if not trades_path.exists():
        raise SystemExit(f"[orb-dev-gate] missing {trades_path}; run scripts/run_orb_dev_wf.py first")
    trades = pd.read_parquet(trades_path)
    print(f"[orb-dev-gate] {len(trades):,} trades", flush=True)

    # Cost stress: 2x slippage re-run.
    print(f"[orb-dev-gate] running 2x-slippage cost stress...", flush=True)
    bars = read_bars(root=bars_root, symbol=engine.symbol, partition="dev", dev_only=True)
    calendar = pd.DataFrame(columns=["timestamp_utc", "currency", "impact"])
    stress_pf = _cost_stress_pf(engine, folds, bars, calendar, trend_filter=trend_filter)
    print(f"[orb-dev-gate] cost-stress PF = {stress_pf:.3f}", flush=True)

    report = evaluate_secondary(trades, cost_stress_pf=stress_pf, min_trade_count=25)

    suffix = "_filtered" if trend_filter else ""
    out = Path(f"docs/superpowers/plans/orb_dev_gate_report{suffix}_2026-11-11.md")
    lines = [
        "# ORB-NAS100 Dev Gate Report — 2026-11-11",
        "",
        f"**Trades (dev, 7-fold OOS):** {report.details['trade_count']}",
        f"**PF:** {report.details['pf']:.4f}  (G1 ≥ 1.3: {'PASS' if report.G1_pass else 'FAIL'})",
        f"**Trade count:** {report.details['trade_count']}  (G2 ≥ 25 relaxed floor: {'PASS' if report.G2_pass else 'FAIL'})",
        f"**All folds net-positive:** {'YES' if report.G3_pass else 'NO'}  (G3: {'PASS' if report.G3_pass else 'FAIL'})",
        f"**R²:** {report.details['r2']:.4f}  (G4 ≥ 0.80: {'PASS' if report.G4_pass else 'FAIL'})",
        f"**Cost-stress PF (2x slippage):** {stress_pf:.3f}  (G5 ≥ 1.1: {'PASS' if report.G5_pass else 'FAIL'})",
        "",
        "### Per-fold pnl_r sum",
        "| Fold | PnL (R) |",
        "|---|---|",
        *[f"| {f} | {pnl:.3f} |" for f, pnl in sorted(report.details['per_fold'].items())],
        "",
        f"### Verdict: {'ADVANCE' if report.all_pass else 'SHELVE'}",
        "",
        "Decision rule: must pass all of G1-G5 to advance to dev MCPT (Task 15).",
        "Honest-expectation base rate for reaching this point green: 20-35%.",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[orb-dev-gate] wrote {out}", flush=True)
    print(f"[orb-dev-gate] all_pass = {report.all_pass}", flush=True)
    print(json.dumps({"G1": report.G1_pass, "G2": report.G2_pass, "G3": report.G3_pass,
                      "G4": report.G4_pass, "G5": report.G5_pass}))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--trend-filter", action="store_true")
    args = ap.parse_args()
    main(trend_filter=args.trend_filter)
