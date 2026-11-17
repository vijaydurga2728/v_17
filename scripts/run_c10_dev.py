"""Cycle 10 Phase 4 entrypoint: development-only Tier 1-3 validation (intraday momentum).

Usage:
  .venv/Scripts/python.exe scripts/run_c10_dev.py [--out-dir out/c10] [--n-perms 100000]

Holdout is never read (see src/v17/backtest/c10_dev_pipeline.py). Anything other
than --n-perms 100000 is labelled a TEST RUN and produces no gate verdict.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from v17.backtest.c10_dev_pipeline import run_dev  # noqa: E402
from v17.validation.c10_mcpt import N_PERMS  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=REPO / "out" / "c10")
    ap.add_argument("--n-perms", type=int, default=N_PERMS)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(args.out_dir / "phase4_dev_run.log", encoding="utf-8")],
    )
    manifest = run_dev(args.out_dir, n_perms=args.n_perms, repo=REPO)
    return 1 if manifest["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
