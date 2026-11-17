"""Cycle 9 smoke test on one dev month of real NAS100 M1 (pre-reg §14).

Checks structural invariants only; prints no performance metrics.
"""
from __future__ import annotations

import numpy as np
import pytest

from v17.backtest.c9_grid import run_grid
from v17.backtest.c9_runner import bars_root, load_m1, prepare
from v17.setups.c9_pdh_pdl import N_TRADABLE_BINS, SYMBOL

pytestmark = pytest.mark.skipif(
    not (bars_root() / SYMBOL / "dev" / "year=2015").exists(), reason="NAS100 M1 data not present"
)


def test_one_dev_month_invariants():
    m1 = load_m1("dev", months=[(2015, 3)])
    assert not m1.empty
    assert m1.attrs["c9_load_audit"]["conflicting_timestamps"] == 0
    assert m1["ts_utc"].max() < np.datetime64("2023-01-01").astype("datetime64[ns]").astype(np.int64)
    prep = prepare(m1, "dev")
    s = prep.sess
    lens = np.diff(s.offsets)
    assert 18 <= s.n_sessions <= 23
    assert (lens <= N_TRADABLE_BINS).all() and (lens >= 20).all()
    assert (s["ask_c"] >= s["bid_c"]).all()
    assert np.isnan(prep.pdh[0]) and np.isfinite(prep.pdh[1:]).sum() >= s.n_sessions - 2
    report, trades = run_grid(prep, 0.0)
    assert len(report) == 12
    for slot_id, tl in trades.items():
        assert len(tl) <= s.n_sessions, slot_id
        if tl.empty:
            continue
        assert np.isfinite(tl["r"]).all()
        assert (tl["sweep_bin"] < tl["confirm_bin"]).all()
        assert (tl["entry_bin"] == tl["confirm_bin"] + 1).all()
        assert (tl["exit_bin"] >= tl["entry_bin"]).all()
        assert tl["date"].is_unique
        assert set(tl["exit_reason"]) <= {"stop_gap", "target_gap", "stop", "target", "eod"}
    _, slip_trades = run_grid(prep, 1.0)
    for slot_id, tl in trades.items():
        # signals never depend on fills: +1pt slippage leaves the trade dates unchanged
        assert list(slip_trades[slot_id]["date"]) == list(tl["date"]), slot_id
