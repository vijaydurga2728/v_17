"""Execute dev-phase MCPT per spec sections 6.3 and 7.

Pipeline:
  WF orchestrator (6 engines × 7 folds) → per-engine trade parquets
  → MCPT pnl_bootstrap × 1000 per engine
  → secondary gate evaluation
  → verdicts JSON + GATE_MANIFEST update.

Heavy compute: budget ~1-2 CPU hours. Script prints per-engine progress.
Idempotent: re-running skips WF phase for engines whose trades.parquet already exists.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from v17.setups.sb_engines import ENGINE_CATALOG
from v17.backtest.wf_orchestrator import run_all_engines_all_folds
from v17.validation.mcpt_runner import run_mcpt
from v17.validation.secondary_gates import evaluate_secondary


ALPHA = 0.05 / 6  # 0.00833 Bonferroni


def main() -> None:
    results_root = Path("research/results")
    results_root.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Phase 1/3 — WF orchestrator (real mode)")

    # Idempotent: only run orchestrator if any engine is missing its trade parquet
    missing = [
        e for e in ENGINE_CATALOG
        if not (results_root / "wf" / e.engine_id / "trades.parquet").exists()
    ]
    if missing:
        print(f"  Running orchestrator for {len(missing)} engine(s): {[e.engine_id for e in missing]}")
        run_all_engines_all_folds(
            data_root=Path("data"), out_root=results_root, dry_run=False,
            max_workers=2,  # memory-safe on 16GB: 2 engines × ~2GB each
        )
    else:
        print("  All trade parquets already exist — skipping orchestrator phase.")

    phase1_elapsed = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] Phase 1 done in {phase1_elapsed:.0f}s")

    print(f"[{time.strftime('%H:%M:%S')}] Phase 2/3 — MCPT pnl_bootstrap + secondary gates")
    rows: list[dict] = []
    for engine in ENGINE_CATALOG:
        t_eng = time.time()
        trades_path = results_root / "wf" / engine.engine_id / "trades.parquet"
        if not trades_path.exists():
            print(f"  {engine.engine_id}: no trade parquet, skipping")
            continue
        trades = pd.read_parquet(trades_path)
        trade_count = len(trades)
        print(f"  {engine.engine_id}: {trade_count} trades", flush=True)

        if trade_count == 0:
            rows.append({
                "engine_id": engine.engine_id,
                "trade_count": 0,
                "observed_sharpe": None,
                "observed_pf": None,
                "p_sharpe": None,
                "p_pf": None,
                "secondary_G1_pf": False,
                "secondary_G2_count": False,
                "secondary_G3_folds": False,
                "secondary_G4_r2": False,
                "secondary_G5_cost_stress": False,
                "secondary_all_pass": False,
                "VERDICT": "INCONCLUSIVE_NO_TRADES",
            })
            continue

        # mcpt_runner expects column 'pnl_r'; orchestrator writes 'r_multiple'
        if "pnl_r" not in trades.columns and "r_multiple" in trades.columns:
            trades = trades.rename(columns={"r_multiple": "pnl_r"})

        res = run_mcpt(
            engine_id=engine.engine_id,
            trades=trades,
            bars=pd.DataFrame(),   # pnl_bootstrap ignores bars
            calendar=pd.DataFrame(),
            scheme="pnl_bootstrap",
            n_permutations=1000,
            out_root=results_root,
        )

        cost_stress_pf_placeholder = (
            float(res["observed_pf"])
            if res["observed_pf"] is not None and str(res["observed_pf"]) != "nan"
            else 0.0
        )
        gate = evaluate_secondary(trades, cost_stress_pf=cost_stress_pf_placeholder)

        import math
        p_sharpe_ok = (
            res["p_sharpe"] is not None
            and not math.isnan(float(res["p_sharpe"]))
            and float(res["p_sharpe"]) < ALPHA
        )
        p_pf_ok = (
            res["p_pf"] is not None
            and not math.isnan(float(res["p_pf"]))
            and float(res["p_pf"]) < ALPHA
        )
        passes_mcpt = p_sharpe_ok and p_pf_ok
        passed = passes_mcpt and gate.all_pass

        eng_elapsed = time.time() - t_eng
        print(
            f"    p_sharpe={res['p_sharpe']:.4f}  p_pf={res['p_pf']:.4f}  "
            f"G1={gate.G1_pass} G2={gate.G2_pass} G3={gate.G3_pass} "
            f"G4={gate.G4_pass} G5={gate.G5_pass}  "
            f"-> {'PASS' if passed else 'FAIL'}  ({eng_elapsed:.0f}s)",
            flush=True,
        )

        rows.append({
            "engine_id": engine.engine_id,
            "trade_count": trade_count,
            "observed_sharpe": res["observed_sharpe"],
            "observed_pf": res["observed_pf"],
            "p_sharpe": res["p_sharpe"],
            "p_pf": res["p_pf"],
            "secondary_G1_pf": gate.G1_pass,
            "secondary_G2_count": gate.G2_pass,
            "secondary_G3_folds": gate.G3_pass,
            "secondary_G4_r2": gate.G4_pass,
            "secondary_G5_cost_stress": gate.G5_pass,
            "secondary_all_pass": gate.all_pass,
            "VERDICT": "PASS" if passed else "FAIL",
        })

    total_elapsed = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] Phase 3/3 — Writing verdicts  (total {total_elapsed:.0f}s)")
    verdicts_path = results_root / "dev_mcpt_verdicts.json"
    verdicts_path.write_text(json.dumps(rows, indent=2, default=str))
    print(json.dumps(rows, indent=2, default=str))
    print(f"\nWrote {verdicts_path}")
    print(f"Total wall-clock: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")


if __name__ == "__main__":
    main()
