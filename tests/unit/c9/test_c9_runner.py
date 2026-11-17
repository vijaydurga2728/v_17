"""Cycle 9 runner: data-integrity (IMPL-10) and Tier 1 Sharpe edge cases (IMPL-11)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.backtest.c9_runner import DataIntegrityError, dedupe_m1, metrics, tier1_pass


def _m1(ts: list[int], bid_c: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"ts_utc": ts, "bid_c": bid_c, "ask_c": [x + 1 for x in bid_c]})


def test_exact_duplicates_dropped_and_counted():
    clean, audit = dedupe_m1(_m1([1, 2, 2, 3, 3, 3], [10, 11, 11, 12, 12, 12]))
    assert list(clean["ts_utc"]) == [1, 2, 3]
    assert audit == {"rows_in": 6, "exact_duplicates_dropped": 3, "conflicting_timestamps": 0}


def test_conflicting_rows_raise():
    with pytest.raises(DataIntegrityError, match="1 timestamps have conflicting"):
        dedupe_m1(_m1([1, 2, 2, 3], [10, 11, 11.5, 12]))


def test_no_duplicates_passthrough():
    df = _m1([1, 2, 3], [10, 11, 12])
    clean, audit = dedupe_m1(df)
    assert clean.equals(df) and audit["exact_duplicates_dropped"] == 0


@pytest.mark.parametrize(("r", "expected"), [
    ([0.5] * 120, np.inf),       # identical positive R: Sharpe +inf, not NaN
    ([0.0] * 120, 0.0),
    ([-0.5] * 120, -np.inf),
    ([2.0], np.inf),             # single trade: no dispersion
])
def test_zero_variance_sharpe(r, expected):
    assert metrics(np.array(r))["sharpe"] == expected


def test_tier1_sharpe_gate_equals_mean_sign():
    # identical positive R passes the Sharpe gate (and all other gates: PF inf, dd 0, n 120)
    assert tier1_pass(metrics(np.array([0.5] * 120)))
    assert not tier1_pass(metrics(np.array([-0.5] * 120)))
    rng = np.random.default_rng(0)
    for _ in range(50):
        r = rng.normal(0, 1, 150)
        m = metrics(r)
        assert (m["sharpe"] >= 0) == (r.mean() >= 0)


def test_zero_trades_fail_tier1():
    assert not tier1_pass(metrics(np.array([])))
