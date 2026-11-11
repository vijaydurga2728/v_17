"""Windows-sequential fallback regression test for wf_orchestrator.

Handoff line 69: ProcessPoolExecutor on Windows can hang silently. This
test confirms dry_run completes in bounded wall-clock time with the
sequential-on-Windows default active.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.xfail(reason="engine_runner.py deferred to Task 12", strict=False, run=False)
def test_dry_run_completes_under_60s(tmp_path: Path) -> None:
    from v17.backtest.wf_orchestrator import run_all_engines_all_folds

    t0 = time.monotonic()
    run_all_engines_all_folds(
        data_root=tmp_path / "data",
        out_root=tmp_path / "out",
        dry_run=True,
        max_workers=2,
    )
    elapsed = time.monotonic() - t0

    assert elapsed < 60, f"orchestrator dry_run took {elapsed:.1f}s; Windows hang regression"
    # Every ENGINE_CATALOG entry should have written a trades.parquet.
    from v17.setups.sb_engines import ENGINE_CATALOG
    for engine in ENGINE_CATALOG:
        out = tmp_path / "out" / "wf" / engine.engine_id / "trades.parquet"
        assert out.exists(), f"missing {out}"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only invariant")
def test_windows_default_is_sequential() -> None:
    os.environ.pop("V17_ORCH_PARALLEL", None)
    import importlib
    import v17.backtest.wf_orchestrator as orch
    importlib.reload(orch)
    assert orch._FORCE_SEQUENTIAL_ON_WINDOWS is True
