"""Cycle 9 deterministic rule tests (pre-reg §14 items a-f + ADR 001 B-F)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.setups import c9_pdh_pdl as c9
from v17.setups.c9_pdh_pdl import Slot, levels, simulate

from .conftest import make_sessions

DAY0 = [(100.0, 110.0, 90.0, 100.0)]  # PDH 110, PDL 90 for day 1
FLAT = (100.0, 100.5, 99.5, 100.0)
LONG1 = Slot(0.0, "long_only", 1)
SHORT1 = Slot(0.0, "short_only", 1)


def _run(days, slot=LONG1, spread=0.0, slip=0.0, atr=2.0):
    s = make_sessions(days, spread=spread)
    pdh, pdl = levels(s)
    atrp = np.full(len(s.bins), atr)
    return simulate(s, pdh, pdl, atrp, slot, slip)


def _long_day(*after_entry):
    # bar0 flat, bar1 low sweep (l 89 < 90, c 92 > 90), bar2 confirms (c 94 > h 93),
    # bar3 = entry bar (open 95).
    return [FLAT, (92.0, 93.0, 89.0, 92.0), (92.0, 94.5, 91.5, 94.0), *after_entry]


# ----------------------------------------------------------------- happy path
def test_long_target_hit():
    tl = _run([DAY0, _long_day((95.0, 96.0, 94.0, 95.5), (95.5, 111.0, 95.0, 109.0))])
    assert len(tl) == 1
    t = tl.iloc[0]
    assert (t.sweep_bin, t.confirm_bin, t.entry_bin, t.exit_bin) == (1, 2, 3, 24)  # last bar = bin 24
    assert t.entry_px == 95.0 and t.stop == 89.0 and t.target == 110.0
    assert t.exit_reason == "target" and t.exit_px == 110.0
    assert t.r == pytest.approx((110 - 95) / 6)
    assert t.rr_at_entry == pytest.approx(15 / 6)


def test_short_mirror_target_hit():
    day = [FLAT, (108.0, 111.0, 107.0, 108.0), (108.0, 108.5, 105.5, 106.0),
           (105.0, 106.0, 104.0, 104.5), (104.5, 105.0, 89.0, 91.0)]
    tl = _run([DAY0, day], slot=SHORT1)
    t = tl.iloc[0]
    assert t.side == "short" and t.entry_px == 105.0 and t.stop == 111.0 and t.target == 90.0
    assert t.exit_reason == "target" and t.exit_px == 90.0
    assert t.r == pytest.approx((105 - 90) / 6)


def test_stop_buffer_uses_atr_prev_at_sweep_bar():
    tl = _run([DAY0, _long_day((95.0, 96.0, 94.0, 95.5))], slot=Slot(0.10, "long_only", 1), atr=10.0)
    assert tl.iloc[0].stop == pytest.approx(89.0 - 0.10 * 10.0)


# --------------------------------------------------------- sweep boundaries (c)
@pytest.mark.parametrize("sweep_bar", [
    (92.0, 93.0, 90.0, 92.0),   # low touches PDL exactly: not beyond -> no sweep
    (92.0, 93.0, 89.0, 90.0),   # closes exactly at PDL: not back inside -> no sweep
    (88.0, 89.0, 87.0, 88.0),   # closes below PDL: breakdown, not sweep
])
def test_no_sweep_on_boundaries(sweep_bar):
    day = [FLAT, sweep_bar, (92.0, 99.0, 91.0, 98.0), (98.0, 99.0, 97.0, 98.0)]
    assert _run([DAY0, day]).empty


def test_no_levels_without_previous_full_day():
    s = make_sessions([DAY0, _long_day((95.0, 96.0, 94.0, 95.5))], prev_ok=[False, False])
    pdh, pdl = levels(s)
    assert np.isnan(pdh).all() and np.isnan(pdl).all()
    assert simulate(s, pdh, pdl, np.full(len(s.bins), 2.0), LONG1).empty


def test_atr_undefined_mutes_candidate():
    s = make_sessions([DAY0, _long_day((95.0, 96.0, 94.0, 95.5))])
    pdh, pdl = levels(s)
    atrp = np.full(len(s.bins), 2.0)
    atrp[2] = np.nan  # sweep bar index 2 in stream (DAY0 has 1 bar)
    assert simulate(s, pdh, pdl, atrp, LONG1).empty


# ------------------------------------------- confirmation window (ADR 001 C/F)
def test_nconf1_invalidates_then_later_candidate_trades():
    day = [FLAT,
           (92.0, 93.0, 89.0, 92.0),    # 1 candidate
           (92.0, 92.8, 91.0, 92.5),    # 2 no confirm -> window (n=1) expires
           (92.0, 92.6, 89.5, 91.0),    # 3 new candidate (h 92.6)
           (91.0, 93.5, 90.5, 93.0),    # 4 confirms candidate 3 (c 93 > 92.6)
           (93.0, 94.0, 92.0, 93.5)]    # 5 entry, EOD
    t = _run([DAY0, day]).iloc[0]
    assert (t.sweep_bin, t.confirm_bin, t.entry_bin) == (3, 4, 24)  # entry on last bar = bin 24


def test_bars_inside_expired_window_are_not_rescanned():
    # IMPL-3 (decided 2026-11-17): candidate at bar 1, n_conf=2 window = bars 2-3.
    # Bar 2 itself qualifies as a sweep and bar 4 would confirm it (c 93.2 > h 92.9),
    # but bar 2 lies inside candidate 1's expired window -> must NOT be a candidate.
    day = [FLAT,
           (92.0, 93.5, 89.0, 92.0),    # 1 candidate (h 93.5)
           (92.0, 92.9, 89.5, 91.0),    # 2 sweep-shaped, inside window
           (91.0, 92.0, 90.5, 91.5),    # 3 no confirm -> window expires
           (91.5, 93.4, 91.0, 93.2),    # 4 > bar-2 high only; < bar-1 high
           (93.2, 94.0, 93.0, 93.5)]
    assert _run([DAY0, day], slot=Slot(0.0, "long_only", 2)).empty


def test_scan_resumes_right_after_expired_window():
    day = [FLAT,
           (92.0, 93.5, 89.0, 92.0),    # 1 candidate
           (92.0, 92.9, 91.0, 92.5),    # 2 window
           (92.0, 92.8, 91.0, 92.4),    # 3 window end, expired
           (92.0, 92.6, 89.5, 91.0),    # 4 = k+N_conf+1: new candidate
           (91.0, 93.5, 90.5, 93.0),    # 5 confirms (c 93 > 92.6)
           (93.0, 94.0, 92.0, 93.5)]    # 6 entry
    t = _run([DAY0, day], slot=Slot(0.0, "long_only", 2)).iloc[0]
    assert (t.sweep_bin, t.confirm_bin, t.entry_bin) == (4, 5, 24)


def test_nconf2_confirms_within_second_bar():
    day = [FLAT, (92.0, 93.0, 89.0, 92.0), (92.0, 92.8, 91.0, 92.5),
           (92.5, 94.0, 92.0, 93.5), (93.5, 94.0, 93.0, 93.8)]
    assert _run([DAY0, day]).empty  # n_conf=1: bar 2 fails, bar 3 is not a sweep
    t = _run([DAY0, day], slot=Slot(0.0, "long_only", 2)).iloc[0]
    assert (t.sweep_bin, t.confirm_bin, t.entry_bin) == (1, 3, 24)


def test_extension_beyond_swept_level_does_not_invalidate():
    # ADR 001 F: bar 2 extends below the sweep low before bar 3 confirms (n_conf=2).
    day = [FLAT, (92.0, 93.0, 89.0, 92.0), (92.0, 92.5, 88.0, 91.0),
           (91.0, 94.0, 90.5, 93.5), (93.5, 94.0, 93.0, 93.8)]
    t = _run([DAY0, day], slot=Slot(0.0, "long_only", 2)).iloc[0]
    assert (t.sweep_bin, t.confirm_bin) == (1, 3)


def test_confirmation_on_last_bar_gives_no_trade():
    assert _run([DAY0, _long_day()]).empty


def test_one_trade_per_side_per_day():
    day = _long_day((95.0, 95.5, 88.0, 89.0),          # 3 entry bar, stopped out
                    (89.5, 90.0, 89.0, 92.0),          # 4 second sweep
                    (92.0, 95.0, 91.0, 94.5),          # 5 would confirm
                    (94.5, 95.0, 94.0, 94.8))          # 6
    tl = _run([DAY0, day])
    assert len(tl) == 1 and tl.iloc[0].exit_reason == "stop"


# ------------------------------------------------- fill priority (d), (e)
def test_same_bar_stop_and_target_assumes_stop():
    tl = _run([DAY0, _long_day((95.0, 96.0, 94.0, 95.5), (95.5, 111.0, 88.0, 100.0))])
    t = tl.iloc[0]
    assert t.exit_reason == "stop" and t.exit_px == 89.0 and t.r == pytest.approx(-1.0)


def test_adverse_gap_fills_at_open():
    tl = _run([DAY0, _long_day((95.0, 96.0, 94.0, 95.5), (87.0, 88.0, 86.0, 87.5))])
    t = tl.iloc[0]
    assert t.exit_reason == "stop_gap" and t.exit_px == 87.0
    assert t.r == pytest.approx((87 - 95) / 6)


def test_favorable_gap_fills_at_open():
    tl = _run([DAY0, _long_day((95.0, 96.0, 94.0, 95.5), (112.0, 113.0, 111.0, 112.5))])
    t = tl.iloc[0]
    assert t.exit_reason == "target_gap" and t.exit_px == 112.0


def test_stop_checked_on_entry_bar():
    tl = _run([DAY0, _long_day((95.0, 96.0, 88.5, 90.0), (90.0, 111.0, 89.5, 110.0))])
    assert tl.iloc[0].exit_reason == "stop" and tl.iloc[0].exit_bin == 3


def test_eod_exit_at_last_bar_close_bid():
    tl = _run([DAY0, _long_day((95.0, 96.0, 94.0, 95.5), (95.5, 97.0, 95.0, 96.5))], spread=1.0)
    t = tl.iloc[0]
    assert t.exit_reason == "eod" and t.exit_bin == 24
    assert t.entry_px == 95.5 and t.exit_px == 96.0  # ask_o entry, bid_c exit


def test_slippage_is_adverse_on_every_fill():
    day = [FLAT, (108.0, 111.0, 107.0, 108.0), (108.0, 108.5, 105.5, 106.0),
           (105.0, 106.0, 104.0, 104.5), (104.5, 105.0, 104.0, 104.2)]
    long_t = _run([DAY0, _long_day((95.0, 96.0, 94.0, 95.5), (95.5, 97.0, 95.0, 96.5))],
                  slip=1.0).iloc[0]
    assert long_t.entry_px == 96.0 and long_t.exit_px == 95.5
    short_t = _run([DAY0, day], slot=SHORT1, slip=1.0).iloc[0]
    assert short_t.entry_px == 104.0 and short_t.exit_px == 105.2


# ------------------------------------------------------------ levels (b)
def test_pdh_pdl_from_previous_session_and_property():
    rng = np.random.default_rng(0)
    days = []
    for _ in range(30):
        c = 100 + rng.normal(0, 1, 25).cumsum()
        days.append([(x, x + abs(rng.normal()), x - abs(rng.normal()), x) for x in c])
    s = make_sessions(days)
    pdh, pdl = levels(s)
    for d in range(1, 30):
        a, b = s.offsets[d - 1], s.offsets[d]
        assert pdh[d] == s["mid_h"][a:b].max() and pdl[d] == s["mid_l"][a:b].min()
        assert pdh[d] >= pdl[d]
        prev_close = s["mid_c"][b - 1]
        assert pdl[d] <= prev_close <= pdh[d]


# --------------------------------------------------------------- ATR (f)
def test_atr_seed_and_no_lookahead():
    rng = np.random.default_rng(1)
    days = []
    for _ in range(3):
        c = 100 + rng.normal(0, 1, 25).cumsum()
        days.append([(x, x + 0.5 + rng.random(), x - 0.5 - rng.random(), x + rng.normal(0, .2))
                     for x in c])
    s = make_sessions(days)
    a = c9.atr_prev(s)
    h, lo, c = s["mid_h"], s["mid_l"], s["mid_c"]
    tr = np.maximum(h[1:] - lo[1:], np.maximum(abs(h[1:] - c[:-1]), abs(lo[1:] - c[:-1])))
    assert np.isnan(a[:15]).all()
    assert a[15] == pytest.approx(tr[:14].mean())             # ATR[14] seeded from TR[1..14]
    assert a[16] == pytest.approx((tr[:14].mean() * 13 + tr[14]) / 14)
    for i in (20, 40, 60):
        s2 = make_sessions(days)
        for f in ("mid_h", "mid_l", "mid_c"):
            s2.prices[f][i] += 50.0
        a2 = c9.atr_prev(s2)
        np.testing.assert_array_equal(a2[: i + 1], a[: i + 1])  # bar i never feeds atr_prev[<=i]
        assert a2[i + 1] != a[i + 1]


# ------------------------------------------------------------ calendar (a)
def test_full_days_exclude_half_days_and_holidays():
    days = c9.full_rth_days("2015-11-23", "2015-12-31")
    as_str = {str(d) for d in days}
    assert "2015-11-25" in as_str
    assert "2015-11-26" not in as_str   # Thanksgiving
    assert "2015-11-27" not in as_str   # half-day
    assert "2015-12-24" not in as_str   # half-day
    assert "2015-12-31" in as_str


# ------------------------------------------------------------ M15 builder
def _m1_day(date: str, start="09:25", end="16:05", price=100.0) -> pd.DataFrame:
    idx = pd.date_range(f"{date} {start}", f"{date} {end}", freq="1min", tz="America/New_York",
                        inclusive="left")
    n = len(idx)
    mid = price + np.arange(n, dtype=float)
    df = pd.DataFrame({"ts_utc": idx.tz_convert("UTC").asi8})
    for s, off in zip("ohlc", (0.0, 0.4, -0.4, 0.1), strict=True):
        df[f"bid_{s}"] = mid + off - 0.5
        df[f"ask_{s}"] = mid + off + 0.5
    df["bid_volume"] = 1.0
    df["ask_volume"] = 1.0
    return df


@pytest.mark.parametrize("date", ["2020-01-15", "2020-07-15"])  # EST and EDT
def test_build_m15_bins_and_cutoff(date):
    m1 = _m1_day(date)
    days = c9.full_rth_days(date, date)
    m15 = c9.build_m15(m1, days)
    assert list(m15["bin"]) == list(range(25))        # [15:45,16:00) never built
    first = m15.iloc[0]
    # 09:30 is minute 5 of the series (09:25 start)
    assert first["bid_o"] == pytest.approx(100 + 5 - 0.5)
    assert first["bid_c"] == pytest.approx(100 + 19 + 0.1 - 0.5)
    assert first["bid_h"] == pytest.approx(100 + 19 + 0.4 - 0.5)
    assert first["mid_o"] == pytest.approx(100 + 5)
    assert first["n_m1_bars"] == 15
    ts0 = pd.Timestamp(int(first["ts_utc"]), tz="UTC").tz_convert("America/New_York")
    assert (ts0.hour, ts0.minute) == (9, 30)


def test_build_m15_drops_sparse_bins_and_half_days():
    m1 = _m1_day("2020-01-15")
    t = pd.to_datetime(m1["ts_utc"], unit="ns", utc=True).dt.tz_convert("America/New_York")
    in_1000 = (t.dt.hour == 10) & (t.dt.minute < 15)
    m1 = m1[~in_1000 | (t.dt.minute < 4)]          # keep 4 M1 bars in 10:00 bin
    m15 = c9.build_m15(m1, c9.full_rth_days("2020-01-15", "2020-01-15"))
    assert 2 not in set(m15["bin"]) and len(m15) == 24
    half = c9.build_m15(_m1_day("2019-11-29"), c9.full_rth_days("2019-11-29", "2019-11-29"))
    assert half.empty


# ------------------------------------------------------- grid + seeds
def test_twelve_slots_and_seed_examples():
    from v17.validation.c9_mcpt import slot_seed
    slots = c9.all_slots()
    assert len(slots) == 12
    assert slot_seed(Slot(0.0, "long_only", 1)) == 20261116000
    assert slot_seed(Slot(0.10, "short_only", 2)) == 20261116011
    assert slot_seed(Slot(0.0, "long_only", 1), holdout=True) == 20261116500


@pytest.mark.skipif(not c9.HAVE_NUMBA, reason="numba not installed")
def test_numba_matches_pure_python():
    rng = np.random.default_rng(5)
    days = []
    for _ in range(60):
        c = 100 + rng.normal(0, 1.5, 25).cumsum()
        days.append([(x, x + abs(rng.normal()), x - abs(rng.normal()), x + rng.normal(0, .3))
                     for x in c])
    s = make_sessions(days, spread=0.3)
    pdh, pdl = levels(s)
    atrp = c9.atr_prev(s)
    np.testing.assert_array_equal(
        atrp, c9._atr_prev_core.py_func(s["mid_h"], s["mid_l"], s["mid_c"], 14))
    p = s.prices
    for slot in c9.all_slots():
        args = (1 if slot.direction == "long_only" else -1, slot.sweep_buffer, slot.n_conf, 1.0,
                s.offsets, pdh, pdl, atrp, c9.entry_eligible(s), p["bid_o"], p["bid_h"], p["bid_l"], p["bid_c"],
                p["ask_o"], p["ask_h"], p["ask_l"], p["ask_c"], p["mid_h"], p["mid_l"], p["mid_c"])
        j_i, j_f, _ = c9._simulate_core(*args)
        p_i, p_f, _ = c9._simulate_core.py_func(*args)
        np.testing.assert_array_equal(j_i, p_i)
        np.testing.assert_allclose(j_f, p_f, rtol=0, atol=1e-12)


# ------------------------------------------------- IMPL-8 missing final bin
def test_session_without_final_bin_is_not_entry_eligible():
    days = [DAY0, _long_day((95.0, 96.0, 94.0, 95.5), (95.5, 111.0, 95.0, 109.0))]
    s = make_sessions(days, final_bin=False)            # last bar labelled bin 4, not 24
    pdh, pdl = levels(s)
    assert not c9.entry_eligible(s)[1]
    assert simulate(s, pdh, pdl, np.full(len(s.bins), 2.0), LONG1).empty
    s_ok = make_sessions(days)                          # identical prices, final bin present
    assert len(simulate(s_ok, *levels(s_ok), np.full(len(s_ok.bins), 2.0), LONG1)) == 1


def test_ineligible_day_still_supplies_levels_to_next_day():
    s = make_sessions([DAY0, [FLAT, FLAT], [FLAT]], final_bin=False)
    pdh, _ = levels(s)
    assert pdh[2] == 100.5  # from day 1 even though day 1 is not entry-eligible
