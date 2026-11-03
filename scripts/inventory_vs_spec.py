# scripts/inventory_vs_spec.py
"""Inventory existing modules against spec section 15 phases.

Usage: python scripts/inventory_vs_spec.py > research/audits/code_inventory_2026-11-03.md
"""
from pathlib import Path

ROOT = Path(__file__).parent.parent / "src" / "v17"

SPEC_REQUIREMENTS = [
    ("Dukascopy paired bid/ask ingest", "data/dukascopy_csv.py", "P2"),
    ("Parquet store with partition tag", "data/parquet_store.py", "P2"),
    ("Partition guard (holdout seal)", "data/partition_guard.py", "P2"),
    ("Finnhub calendar backfill", "data/calendar/__init__.py", "P1"),
    ("D1 bias calculator (SB-A1)", "structure/bias.py", "P5"),
    ("FVG detector (causal)", "structure/fvg.py", "P5"),
    ("MSS detector (close-based)", "structure/mss.py", "P5"),
    ("Session boundaries NY/London", "structure/session.py", "P5"),
    ("Silver Bullet FSM", "setups/silver_bullet_fsm.py", "P5"),
    ("Instrument spec (pip sizes)", "common/instrument_spec.py", "P5"),
    ("Cost model (bid/ask + commission)", "backtest/cost.py", "P2+P5"),
    ("Fill model (limit, market)", "backtest/fills.py", "P5"),
    ("Backtest event loop", "backtest/loop.py", "P5"),
    ("Walk-forward harness", "backtest/walkforward.py", "P7"),
    ("MCPT harness", "validation/mcpt.py", "P8"),
    ("Validation gate", "validation/gate.py", "P10"),
    ("Validation thresholds", "validation/thresholds.py", "P10"),
    ("Risk engine (position sizing)", "risk/engine.py", "P5"),
    ("Risk rules (circuit breakers)", "risk/risk_rules.py", "P5"),
    ("MT5 reconciliation", "live/reconcile.py", "future-live"),
]


def main():
    print("# Code Inventory vs Spec Requirements\n")
    print("**Date:** 2026-11-03\n")
    print("**Reference:** `docs/superpowers/specs/2026-11-03-silver-bullet-6-engine-doctrine-test-design.md` section 15\n")
    print()
    print("| Requirement | Spec Phase | File | Exists | LOC | Status |")
    print("|---|---|---|---|---|---|")
    for req, path, phase in SPEC_REQUIREMENTS:
        f = ROOT / path
        exists = f.exists()
        loc = sum(1 for _ in f.open(encoding="utf-8")) if exists and f.is_file() else 0
        status = "present" if exists and loc > 10 else ("stub" if exists else "missing")
        marker = "yes" if exists else "no"
        print(f"| {req} | {phase} | `src/v17/{path}` | {marker} | {loc} | {status} |")
    print()


if __name__ == "__main__":
    main()
