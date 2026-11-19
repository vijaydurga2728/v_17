"""Cycle 23 Phase 2: gate 6 event parity + frozen descriptive metrics (synthetic only)."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import c21_fixtures as F
from c21_fixture_parity import XNYS
from c21_reference_impl import RefMarket, run_day

from v17.c23_visual.event_export import export
from v17.c23_visual.metrics import atr14, candidate_metrics
from v17.c23_visual.parity import compare, engine_stream, reference_stream
from v17.smc_sb.config import BASELINE
from v17.smc_sb.data import build_market

BASE = F.Fixture("base", "base day", F.m1_frame(F.day_rows(F.BASE)))
MIRROR = F.Fixture("base_short", "mirrored base day", F.mirror(F.m1_frame(F.day_rows(F.BASE))))
FIXTURES = [BASE, MIRROR, *F.fixtures()]


def _streams(f: F.Fixture):
    cfg = dataclasses.replace(BASELINE, entry_model=f.model, order_expiry=f.expiry)
    mk = build_market("NAS100", f.m1, xnys=XNYS, early_close=f.early)
    recs, ledger, _ = export(mk, cfg, [F.DAY])
    trace: list[tuple] = []
    reason, _ = run_day(
        RefMarket(f.m1, "NAS100", xnys=XNYS, early=f.early),
        F.DAY,
        model=f.model,
        expiry=f.expiry,
        trace=trace,
    )
    return mk, ledger, engine_stream(ledger, recs[0].result), reference_stream(trace, reason)


@pytest.mark.parametrize("f", FIXTURES, ids=[f.name for f in FIXTURES])
def test_gate6_event_parity(f: F.Fixture) -> None:
    _, _, eng, ref = _streams(f)
    assert compare(eng, ref) == []


def test_gate6_rescan_path_has_two_setups_and_cancel() -> None:
    f = next(x for x in FIXTURES if x.name == "one_pending_then_rescan")
    _, _, eng, _ = _streams(f)
    stages = [s[0] for s in eng]
    assert stages.count("sweep") == 2
    assert "order_expired_cancelled" in stages
    assert eng[-1] == ("result", "unfilled_expired")


def test_gate6_short_side_stream() -> None:
    _, _, eng, _ = _streams(MIRROR)
    sweep = eng[0]
    assert sweep[:3] == ("sweep", eng[0][1], "PDH")
    assert sweep[3] == pytest.approx(200 - 99.0)


def test_gate6_compare_detects_differences() -> None:
    _, _, eng, ref = _streams(BASE)
    shifted = [(*ref[0][:1], ref[0][1] + 60_000_000_000, *ref[0][2:]), *ref[1:]]
    assert compare(eng, shifted)  # time shifted by one minute
    repriced = [ref[0], (ref[1][0], ref[1][1], ref[1][2] + 1e-6), *ref[2:]]
    assert compare(eng, repriced)  # MSS level off by 1e-6
    assert compare(eng, ref[:-2] + ref[-1:])  # missing exit event
    assert compare(eng, [*ref[:-1], ("result", "no_mss")])  # different result


def test_trace_hook_does_not_change_reference_result() -> None:
    for f in FIXTURES:
        rm = RefMarket(f.m1, "NAS100", xnys=XNYS, early=f.early)
        a = run_day(rm, F.DAY, model=f.model, expiry=f.expiry)
        b = run_day(rm, F.DAY, model=f.model, expiry=f.expiry, trace=[])
        assert str(a) == str(b)


def test_metrics_base_day_hand_computed() -> None:
    mk, ledger, _, _ = _streams(BASE)
    # ATR14 at the 10:20 displacement candle = mean TR of 09:10..10:15 candles = 8.8 / 14 (hand-computed)
    disp_ns = pd.Timestamp("2024-03-18 10:20", tz="America/New_York").value
    kk = int((mk.c5.start.to_numpy() == disp_ns).nonzero()[0][0])
    assert atr14(mk.c5, kk) == pytest.approx(8.8 / 14)
    m = candidate_metrics(mk, ledger)
    assert m.sweep_depth == pytest.approx(0.5)  # PDL 99.0, sweep low 98.5
    assert m.sweep_close_inside is True  # 10:00 candle closes 99.4 > 99.0
    assert m.disp_body_ratio == pytest.approx(1.2 / 1.4)
    assert m.disp_range_atr == pytest.approx(1.4 / (8.8 / 14))
    assert m.fvg_size_atr == pytest.approx(0.4 / (8.8 / 14))


def test_metrics_rejected_before_fvg_are_partial() -> None:
    f = next(x for x in FIXTURES if x.name == "early_close_no_entry")
    mk, ledger, _, _ = _streams(f)
    m = candidate_metrics(mk, ledger)
    assert m.sweep_close_inside is None
    assert m.fvg_size_atr != m.fvg_size_atr  # NaN
