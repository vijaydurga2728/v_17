"""Regression tests for review-1 corrections: R12 re-scan, R15 gap-through, R18 creation time, R19 NWOG
times / missing bars, R27 crossed-quote sessions, R28 early-close, R29 XNYS-only daily table, R30 repeats."""

from __future__ import annotations

import dataclasses
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from v17.smc_sb.config import BASELINE
from v17.smc_sb.data import build_market, repeat_mask
from v17.smc_sb.engine import Engine
from v17.smc_sb.execution import run_exit
from v17.smc_sb.fvg import find_fvg
from v17.smc_sb.liquidity import day_levels, nwog, select_target
from v17.smc_sb.session import ny_ns
from v17.smc_sb.structure import pivot_flags
from v17.smc_sb.sweep import Ref, find_sweep

NY = "America/New_York"


def ns(s: str) -> int:
    return pd.Timestamp(s, tz=NY).value


def mk_rows(synth, rows):
    return synth.build(synth.m1_frame(rows))


# ---------------- R15 gap-through stops ----------------
def test_long_gap_through_stop_exits_at_bid_open_minus_slippage(synth):
    rows = [("2024-03-18 10:31", 100, 100, 100, 100), ("2024-03-18 10:32", 94, 94.5, 93, 94)]
    ex = run_exit(mk_rows(synth, rows), 1, 0, 95.0, 105.0, ns("2024-03-18 16:00"), 0.5)
    # bid open = 94 - 0.1 = 93.9 < stop 95 -> 93.9 - 0.5
    assert ex.reason == "stop" and ex.gap_through and ex.price == pytest.approx(93.4)


def test_short_gap_through_stop_exits_at_ask_open_plus_slippage(synth):
    rows = [("2024-03-18 10:31", 100, 100, 100, 100), ("2024-03-18 10:32", 106, 107, 105.5, 106)]
    ex = run_exit(mk_rows(synth, rows), -1, 0, 105.0, 95.0, ns("2024-03-18 16:00"), 0.5)
    assert ex.reason == "stop" and ex.gap_through and ex.price == pytest.approx(106.1 + 0.5)


def test_non_gap_stop_keeps_stop_price(synth):
    rows = [("2024-03-18 10:31", 100, 100, 100, 100), ("2024-03-18 10:32", 99, 99.5, 94, 95)]
    ex = run_exit(mk_rows(synth, rows), 1, 0, 95.0, 105.0, ns("2024-03-18 16:00"), 0.5)
    assert ex.reason == "stop" and not ex.gap_through and ex.price == 94.5


def test_gap_rule_applies_on_fill_bar(synth):
    rows = [("2024-03-18 10:31", 94, 101, 93, 94)]  # fill bar opens below the stop
    ex = run_exit(mk_rows(synth, rows), 1, 0, 95.0, 105.0, ns("2024-03-18 16:00"), 0.5)
    assert ex.idx == 0 and ex.gap_through and ex.price == pytest.approx(93.9 - 0.5)


# ---------------- R18 / R29 levels and creation times ----------------
def test_pdh_pdl_from_previous_xnys_session_created_1700(synth):
    # 2024-03-29 is Good Friday (XNYS holiday) but the CFD trades: it must be skipped (R29)
    rows = [
        ("2024-03-27 12:00", 100, 110, 90, 100),
        ("2024-03-28 12:00", 100, 120, 95, 100),
        ("2024-03-29 03:00", 100, 130, 80, 100),  # non-XNYS session
        ("2024-04-01 12:00", 100, 101, 99, 100),
    ]
    mk = mk_rows(synth, rows)
    assert dt.date(2024, 3, 29) in mk.non_xnys_sessions
    assert pd.Timestamp("2024-03-29") not in mk.daily.index
    day = dt.date(2024, 4, 1)
    lv = day_levels(mk, day, mk.day_pos(pd.Timestamp(day)))
    assert (lv.pdh, lv.pdl) == (120, 95)  # Thursday 2024-03-28, not the Good Friday session
    assert lv.pd_created_ns == ns("2024-03-28 17:00")
    assert lv.asia_created_ns == ns("2024-04-01 00:00")


# ---------------- R19 NWOG ----------------
def test_nwog_uses_sunday_1800_open(synth):
    rows = [
        ("2024-03-15 16:59", 100, 100, 100, 100),
        ("2024-03-17 17:30", 150, 150, 150, 150),  # before 18:00: not the NWOG open
        ("2024-03-17 18:00", 102, 102, 102, 102),
    ]
    lo, hi, start = nwog(mk_rows(synth, rows), dt.date(2024, 3, 18))
    assert (lo, hi, start) == (100, 102, ns("2024-03-17 18:00"))


def test_nwog_absent_without_friday_session(synth):
    rows = [("2024-03-13 12:00", 100, 100, 100, 100), ("2024-03-17 18:00", 102, 102, 102, 102)]
    lo, _, _ = nwog(mk_rows(synth, rows), dt.date(2024, 3, 18))
    assert np.isnan(lo)  # last close before Friday 17:00 is Wednesday -> no substitution


# ---------------- R27 crossed-quote sessions ----------------
def test_crossed_quote_session_is_removed_and_next_day_uses_previous_session(synth):
    df = synth.scenario_m1()
    bad_ts = ns("2024-03-14 20:30")  # evening of Thu 2024-03-14 -> trading date Fri 2024-03-15
    row = df.iloc[[0]].copy()
    row["ts_utc"] = bad_ts
    for f in "ohlc":
        row[f"bid_{f}"], row[f"ask_{f}"] = 101.0, 100.9
    df = pd.concat([df, row], ignore_index=True)
    mk = synth.build(df)
    assert mk.excluded_sessions == (dt.date(2024, 3, 15),)
    assert pd.Timestamp("2024-03-15") not in mk.daily.index
    assert not np.any(mk.ts == bad_ts)
    res = Engine(mk, BASELINE).run_day(dt.date(2024, 3, 15))
    assert res.reason == "excluded_session_bad_quotes"
    assert mk.exclusion_reason[dt.date(2024, 3, 15)] == "crossed_quotes"
    # Monday: the Friday daily candle is gone, so the confirmed pivot low at Friday's slot disappears -> neutral
    res2 = Engine(mk, BASELINE).run_day(synth.DAY)
    assert res2.reason == "bias_insufficient_structure"
    # R5a: any window intersecting [Thu 17:00, Fri 17:00) is contaminated; targets created before it are rejected
    assert mk.contaminated(ns("2024-03-14 17:00"), ns("2024-03-18 10:30"))
    assert not mk.contaminated(ns("2024-03-15 17:00"), ns("2024-03-18 10:30"))
    pos = mk.day_pos(pd.Timestamp(synth.DAY))
    lv = day_levels(mk, synth.DAY, pos)
    assert lv.pd_created_ns == ns("2024-03-14 17:00")  # previous valid XNYS session = Thursday
    ts_ = select_target(mk, lv, 1, 101.6, 101.2, ns("2024-03-18 10:30"), 2.0, 0.5, 0.0)
    assert ts_.contaminated and ts_.target is None


# ---------------- R28 early-close ----------------
def test_early_close_day_has_no_entries(synth):
    mk = build_market(
        "NAS100",
        synth.scenario_m1(),
        early_close=[synth.DAY],
        xnys=[d.date() for d in pd.bdate_range("2024-02-01", "2024-03-29")],
    )
    assert Engine(mk, BASELINE).run_day(synth.DAY).reason == "early_close_day"
    assert pd.Timestamp(synth.DAY) in mk.daily.index  # its daily candle stays for later context


# ---------------- R30 repeated bars ----------------
def test_repeated_bars_flagged_and_reported(synth):
    rows = [("2024-03-18 10:00", 100, 101, 99, 100.5)] * 1
    rows += [("2024-03-18 10:01", 100, 101, 99, 100.5), ("2024-03-18 10:02", 100, 101, 99, 100.5)]
    df = synth.m1_frame(rows)
    assert list(repeat_mask(df)) == [False, True, True]
    mk = synth.build(synth.scenario_m1())
    t = Engine(mk, BASELINE).run_day(synth.DAY).trade
    assert t is not None and t["repeated_m1_bars_setup"] == int(
        mk.repeat[mk.idx(ns("2024-03-18 10:00")) : t["fill_i"] + 1].sum()
    )


def test_repeated_flat_bars_create_no_pivot_fvg_or_sweep(synth):
    rows = [(f"2024-03-18 {h}:{m:02d}", 100, 100, 100, 100) for h in (9, 10) for m in range(60)]
    mk = mk_rows(synth, rows)
    ph, pl = pivot_flags(mk.c15.h.to_numpy(), mk.c15.l.to_numpy(), 2, 2)
    assert not ph.any() and not pl.any()
    assert find_fvg(mk.c5, 1, ns("2024-03-18 10:00"), ns("2024-03-18 11:00")) is None
    assert find_fvg(mk.c5, -1, ns("2024-03-18 10:00"), ns("2024-03-18 11:00")) is None
    ref = Ref(
        "PDL", 100.0, ns("2024-03-15 17:00")
    )  # price sits exactly on the ref: never strictly beyond
    s, _ = find_sweep(
        mk, 1, [ref], ns("2024-03-18 10:00"), ns("2024-03-18 11:00"), ns("2024-03-18 10:00")
    )
    assert s is None


# ---------------- R12 one pending order, re-scan after cancellation ----------------
def test_unfilled_order_expires_and_rescan_finds_consumed_ref(synth):
    """Expiry moved to 10:31 (test only): the 10:32 fill never happens -> cancel -> re-scan from 10:31;
    the PDL was consumed by the first sweep, so no distinct setup exists -> 'unfilled_expired'."""
    mk = synth.build(synth.scenario_m1())
    cfg = dataclasses.replace(BASELINE, order_expiry="10:31")
    res = Engine(mk, cfg).run_day(synth.DAY)
    stages = [e["stage"] for e in res.events]
    assert res.reason == "unfilled_expired" and res.trade is None
    assert stages.count("order_created") == 1 and "order_expired_cancelled" in stages
    rescan = [e for e in res.events if e["stage"] == "sweep_scan"][1]
    assert rescan["not_before"].startswith("2024-03-18T10:31")
    assert "consumed_by_earlier_setup" in str(rescan["refs"])
    assert ny_ns(synth.DAY, "10:31") > 0


# ---------------- R31 (proposed) frozen quote side ----------------
def test_frozen_ask_run_excludes_sessions_it_covers(synth):
    px = [100 + 0.01 * k for k in range(120)]
    rows = [
        (f"2024-03-14 {8 + k // 60:02d}:{k % 60:02d}", p, p + 0.5, p - 0.5, p)
        for k, p in enumerate(px)
    ]
    df = synth.m1_frame(rows)
    df.loc[10:50, ["ask_o", "ask_h", "ask_l", "ask_c"]] = 150.0  # ask frozen for 41 bars, bid moves
    df = pd.concat(
        [df, synth.m1_frame([("2024-03-15 10:00", 100, 100.5, 99.5, 100)])], ignore_index=True
    )
    from v17.smc_sb.data import frozen_side_mask

    m = frozen_side_mask(df, 30)
    assert m[11:51].all() and not m[:11].any() and not m[51:].any()
    assert not frozen_side_mask(df, 45).any()  # run of 40 below a 45 threshold
    mk = synth.build(df)
    assert mk.excluded_sessions == (dt.date(2024, 3, 14),)
    assert mk.exclusion_reason[dt.date(2024, 3, 14)] == "frozen_quote_side"
