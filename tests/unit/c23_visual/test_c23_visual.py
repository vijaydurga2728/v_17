"""Cycle 23 Phase 1 gates 1-5 (spec 2026-11-19-cycle23-visual-validation-spec.md §7). Synthetic data only."""

from __future__ import annotations

import dataclasses
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import c21_fixtures as F  # noqa: E402, N812
from c21_fixture_parity import XNYS  # noqa: E402

from v17.c23_visual.annotations import build, decision_view, fingerprint  # noqa: E402
from v17.c23_visual.chart_manifest import chart_id, generate, manifest_violations  # noqa: E402
from v17.c23_visual.event_export import data_fingerprint, export  # noqa: E402
from v17.c23_visual.validation import decision_violations, ledger_violations  # noqa: E402
from v17.smc_sb.config import BASELINE, CONFIG_VERSION  # noqa: E402
from v17.smc_sb.data import build_market  # noqa: E402
from v17.smc_sb.engine import Engine  # noqa: E402
from v17.smc_sb.session import ny_ns  # noqa: E402

FROZEN_FINGERPRINT = "a25af5711afb32d4"  # c21 baseline at commit 0f7054c
FIXTURES = [F.Fixture("base", "base day", F.m1_frame(F.day_rows(F.BASE))), *F.fixtures()]
IDS = [f.name for f in FIXTURES]


def _run(f: F.Fixture):
    cfg = dataclasses.replace(BASELINE, entry_model=f.model, order_expiry=f.expiry)
    mk = build_market("NAS100", f.m1, xnys=XNYS, early_close=f.early)
    recs, ledger, raw = export(mk, cfg, [F.DAY])
    return mk, cfg, recs[0], ledger, raw[0]


def _ny(hhmm: str, day: dt.date = F.DAY) -> int:
    return ny_ns(day, hhmm)


def _ns(x: object) -> int:
    return int(pd.Timestamp(x).value)  # type: ignore[arg-type]


def _scenario(day: dt.date) -> pd.DataFrame:
    """The base fixture day moved to `day` (prior 11 business days of daily bars, 5 m candles, flat tail)."""
    rows: list[tuple] = []
    prior = pd.bdate_range(end=pd.Timestamp(day) - pd.Timedelta(days=1), periods=len(F.PRIOR_H))
    for k, d in enumerate(prior):
        h, lo = F.PRIOR_H[k], F.PRIOR_L[k]
        mid = 101.0 if k == len(F.PRIOR_H) - 1 else (h + lo) / 2
        rows.append((f"{d.date()} 12:00", mid, h, lo, mid))
    for c in F.BASE:
        rows += F.five_min(day.isoformat(), *c)
    t = pd.Timestamp(f"{day} 10:50")
    while t < pd.Timestamp(f"{day} 16:00"):
        rows.append((t.strftime("%Y-%m-%d %H:%M"), 109.2, 109.2, 109.2, 109.2))
        t += pd.Timedelta(minutes=1)
    return F.m1_frame(rows)


# ---------------------------------------------------------------- gate 1: baseline isolation
def test_gate1_baseline_fingerprint_frozen() -> None:
    assert CONFIG_VERSION == "21.2.0"
    assert BASELINE.fingerprint() == FROZEN_FINGERPRINT


@pytest.mark.parametrize("f", FIXTURES, ids=IDS)
def test_gate1_export_does_not_change_engine_output(f: F.Fixture) -> None:
    mk, cfg, _, _, res = _run(f)
    direct = Engine(mk, cfg).run_day(F.DAY)
    assert res.reason == direct.reason
    assert res.trade == direct.trade
    assert str(res.events) == str(direct.events)


# ---------------------------------------------------------------- gate 2: ledger correctness
@pytest.mark.parametrize("f", FIXTURES, ids=IDS)
def test_gate2_ledger_valid_and_deterministic(f: F.Fixture) -> None:
    mk, cfg, rec, ledger, _ = _run(f)
    assert ledger_violations(mk, ledger, cfg) == []
    _, _, rec2, ledger2, _ = _run(f)
    assert [e.model_dump() for e in ledger] == [e.model_dump() for e in ledger2]
    assert rec == rec2
    assert ledger[-1].stage in ("rejected", "exit")
    if rec.result != "trade":
        assert ledger[-1].rejection_reason == rec.result


def test_gate2_categories() -> None:
    got = {f.name: _run(f)[2] for f in FIXTURES}
    assert got["base"].category == "filled" and got["base"].charted
    assert (
        got["early_close_no_entry"].category == "excluded"
        and not got["early_close_no_entry"].charted
    )
    assert got["one_pending_then_rescan"].category == "unfilled_expired"
    assert got["ote_invalid"].category == "rejected_after_sweep"
    assert got["ote_invalid"].near_miss_stage == "ote_proximal_outside_zone"
    assert got["base"].near_miss_stage is None


def test_gate2_non_session_day_is_excluded_and_not_charted() -> None:
    mk = build_market("NAS100", FIXTURES[0].m1, xnys=XNYS, early_close=[])
    recs, ledger, _ = export(mk, BASELINE, [dt.date(2024, 3, 16)])  # Saturday
    assert recs[0].result == "not_xnys_session"
    assert recs[0].category == "excluded" and not recs[0].charted
    assert ledger[0].rejection_reason == "not_xnys_session"


# ---------------------------------------------------------------- gate 3: no lookahead
@pytest.mark.parametrize("f", FIXTURES, ids=IDS)
def test_gate3_decision_view_has_no_future_information(f: F.Fixture) -> None:
    mk, cfg, rec, ledger, _ = _run(f)
    if not rec.charted:
        pytest.skip("not charted")
    assert decision_violations(mk, rec, build(rec, ledger, cfg)) == []


def test_gate3_event_availability_base_day() -> None:
    _, _cfg, rec, ledger, _ = _run(FIXTURES[0])
    av = {e.stage: _ns(e.available_at) for e in ledger}
    assert av["sweep"] == _ny("10:05")  # 10:00 5 m candle must close
    assert av["mss"] == _ny("10:30")  # 15 m candle 10:15-10:30 close
    assert av["fvg"] == _ny("10:30")  # candle 3 (10:25) close
    assert av["order_created"] == _ny("10:30")
    assert av["order_filled"] == _ny("10:33")  # M1 bar 10:32 close
    assert av["exit"] == _ny("10:48")
    assert rec.cut_ns == _ny("10:30") and rec.end_ns == _ny("10:48")
    mss = next(e for e in ledger if e.stage == "mss")
    swing = _ns(str(mss.payload["swing_ts"]))
    assert swing + 3 * 15 * 60 * 10**9 <= av["mss"]  # right=2 pivot confirmed before the MSS


@pytest.mark.parametrize(
    "day", [dt.date(2024, 1, 22), dt.date(2024, 11, 4)], ids=["EST_winter", "after_DST_end"]
)
def test_gate3_dst_session_times(day: dt.date) -> None:
    """Same scenario on EST dates: window/expiry/cut must follow the NY wall clock, not a fixed UTC offset."""
    xn = [d.date() for d in pd.bdate_range(day - dt.timedelta(days=40), day)]
    mk = build_market("NAS100", _scenario(day), xnys=xn, early_close=[])
    recs, ledger, _ = export(mk, BASELINE, [day])
    rec = recs[0]
    assert rec.result == "trade"
    assert rec.cut_ns == ny_ns(day, "10:30")
    assert decision_violations(mk, rec, build(rec, ledger, BASELINE)) == []
    assert (
        pd.Timestamp(rec.cut_ns, tz="UTC").tz_convert("America/New_York").strftime("%H:%M")
        == "10:30"
    )


# ---------------------------------------------------------------- gate 4: exact annotation coordinates
def test_gate4_base_day_annotation_coordinates() -> None:
    _, cfg, rec, ledger, _ = _run(FIXTURES[0])
    annos = build(rec, ledger, cfg)
    by = {(a.panel, a.label): a for a in annos}
    fvg = by[("5m", "FVG")]
    assert (fvg.p0, fvg.p1) == pytest.approx((101.2, 101.6))
    assert (fvg.t0, fvg.t1, fvg.available_ns) == (_ny("10:15"), _ny("11:05"), _ny("10:30"))
    disp = by[("5m", "displacement")]
    assert (disp.t0, disp.t1) == (_ny("10:20"), _ny("10:25"))
    sweep = by[("5m", "sweep")]
    assert (sweep.t0, sweep.p0, sweep.available_ns) == (
        _ny("10:00"),
        pytest.approx(98.5),
        _ny("10:05"),
    )
    assert by[("15m", "swept PDL")].p0 == pytest.approx(99.0)
    mss = by[("15m", "MSS level")]
    assert (mss.t0, mss.t1, mss.p0) == (_ny("09:30"), _ny("10:30"), pytest.approx(102.0))
    assert by[("1m", "limit")].p0 == pytest.approx(101.6)
    assert by[("1m", "stop")].p0 == pytest.approx(101.2)
    assert by[("1m", "target PDH")].p0 == pytest.approx(109.0)
    assert by[("D1", "PDH")].p0 == pytest.approx(109.0) and by[("D1", "PDL")].p0 == pytest.approx(
        99.0
    )
    assert by[("D1", "EQ (discount)")].p0 == pytest.approx(103.0)
    fill = by[("1m", "fill")]
    assert fill.outcome_only and (fill.t0, fill.p0) == (_ny("10:32"), pytest.approx(101.6))
    ex = next(a for a in annos if a.label.startswith("exit target"))
    assert ex.outcome_only and (ex.t0, ex.p0) == (_ny("10:47"), pytest.approx(109.0))
    shown = decision_view(annos, rec.cut_ns or 0)
    assert all(not a.outcome_only for a in shown)
    assert max(a.t1 for a in shown if a.kind in ("hline", "box")) == _ny("10:30")


def test_gate4_gap_stop_exit_annotation() -> None:
    f = next(x for x in FIXTURES if x.name == "gap_long_stop")
    _, cfg, rec, ledger, _ = _run(f)
    ex = next(a for a in build(rec, ledger, cfg) if a.label.startswith("exit stop"))
    assert ex.t0 == _ny("10:35") and ex.p0 == pytest.approx(99.9 - 0.5)


# ---------------------------------------------------------------- gate 5: rendering + reproducibility
def test_gate5_render_manifest_and_resume(tmp_path: Path) -> None:
    out1, out2 = tmp_path / "a", tmp_path / "b"
    expected: dict[str, set[str]] = {}
    for f in FIXTURES:
        mk, cfg, rec, ledger, _ = _run(f)
        fp = data_fingerprint(mk)
        m1 = generate(mk, cfg, [rec], ledger, out1 / f.name, fp)
        m2 = generate(mk, cfg, [rec], ledger, out2 / f.name, fp)
        exp = {chart_id(rec, v) for v in ("decision", "outcome")} if rec.charted else set()
        expected[f.name] = exp
        assert manifest_violations(m1, out1 / f.name, exp) == []
        a = {k: v["annotation_fp"] for k, v in m1["charts"].items()}  # type: ignore[union-attr]
        b = {k: v["annotation_fp"] for k, v in m2["charts"].items()}  # type: ignore[union-attr]
        assert a == b
        assert m1["config_fingerprint"] == cfg.fingerprint() and m1["data_fingerprint"] == fp
    # resume: delete one PNG -> regenerated; others skipped with identical entries
    f = FIXTURES[0]
    mk, cfg, rec, ledger, _ = _run(f)
    d = out1 / f.name
    before = generate(mk, cfg, [rec], ledger, d, data_fingerprint(mk))
    png = d / str(before["charts"][chart_id(rec, "outcome")]["path"])  # type: ignore[index]
    png.unlink()
    after = generate(mk, cfg, [rec], ledger, d, data_fingerprint(mk))
    assert png.exists()
    assert manifest_violations(after, d, expected[f.name]) == []
    assert after["charts"] == before["charts"]


def test_gate5_annotation_fingerprint_changes_with_content() -> None:
    _, cfg, rec, ledger, _ = _run(FIXTURES[0])
    annos = build(rec, ledger, cfg)
    assert fingerprint(annos) == fingerprint(build(rec, ledger, cfg))
    assert fingerprint(annos) != fingerprint(annos[:-1])
