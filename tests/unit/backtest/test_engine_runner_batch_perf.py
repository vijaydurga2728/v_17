"""Perf guard — ORB engine_runner batch wall-clock.

Handoff line 71: batch wall-clock regressed 2 min -> 70 min on 2 symbols × 7
folds when per-symbol preprocessing ran per-fold via pd.concat. ORB engine
runner (Task 12) must preprocess each symbol ONCE and slice the fold loop by
index — never concat.

This test is a placeholder until Task 12 lands; re-enable then.
"""
from __future__ import annotations

import pytest


@pytest.mark.perf
def test_batch_wallclock_single_symbol_under_8min() -> None:
    pytest.skip("perf guard — enable after Task 12 ORB engine_runner exists")
