"""Unit + regression tests for every signal stage (spec §14): session/DST, pivots, bias, sweep, MSS, FVG,
OTE, premium/discount, targets/NWOG, fills, stop/target ordering, data guards."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from v17.smc_sb.config import StrategyConfig
from v17.smc_sb.data import (
    DataIntegrityError,
    HoldoutAccessError,
    build_candles,
    load_m1,
    validate_m1,
    widen_costs,
)
from v17.smc_sb.entry_models import model_b_ok, ote_zone
from v17.smc_sb.execution import find_fill, run_exit
from v17.smc_sb.fvg import find_fvg
from v17.smc_sb.liquidity import DayLevels, nwog, select_target
from v17.smc_sb.market_bias import DailyStructure
from v17.smc_sb.premium_discount import eligible
from v17.smc_sb.session import ny_ns, trading_date_of
from v17.smc_sb.structure import find_mss, latest_confirmed, pivot_flags
from v17.smc_sb.sweep import find_sweep

NY = "America/New_York"
MIN = 60_000_000_000


def ns(s: str) -> int:
    return pd.Timestamp(s, tz=NY).value


def candles(rows: list[tuple[str, float, float, float, float]], minutes: int) -> pd.DataFrame:
    st = np.array([ns(r[0]) for r in rows])
    return pd.DataFrame(
        {
            "start": st,
            "end": st + minutes * MIN,
            "o": [r[1] for r in rows],
            "h": [r[2] for r in rows],
            "l": [r[3] for r in rows],
            "c": [r[4] for r in rows],
        }
    )


# ---------------- session / DST ----------------
def test_ny_clock_handles_dst():
    assert pd.Timestamp(ny_ns(dt.date(2024, 3, 8), "10:00"), tz="UTC").hour == 15  # EST, UTC-5
    assert pd.Timestamp(ny_ns(dt.date(2024, 3, 11), "10:00"), tz="UTC").hour == 14  # EDT, UTC-4
    assert pd.Timestamp(ny_ns(dt.date(2024, 11, 4), "10:00"), tz="UTC").hour == 15


def test_trading_date_rolls_at_17_ny():
    t = np.array(
        [
            ns("2024-03-17 18:00"),
            ns("2024-03-18 16:59"),
            ns("2024-03-18 17:00"),
            ns("2024-03-17 20:30"),
        ]
    )
    got = [str(x) for x in trading_date_of(t, 17)]
    assert got == ["2024-03-18", "2024-03-18", "2024-03-19", "2024-03-18"]


def test_candles_align_to_ny_clock_across_dst():
    t = np.array(
        [
            ns("2024-03-08 10:03"),
            ns("2024-03-08 10:07"),
            ns("2024-03-11 10:03"),
            ns("2024-03-11 10:14"),
        ]
    )
    one = np.ones(4)
    c5 = build_candles(t, one, one, one, one, 5)
    starts = [pd.Timestamp(x, tz="UTC").tz_convert(NY).strftime("%m-%d %H:%M") for x in c5.start]
    assert starts == ["03-08 10:00", "03-08 10:05", "03-11 10:00", "03-11 10:10"]
    c15 = build_candles(t, one, one, one, one, 15)
    assert list(c15.n_m1) == [2, 2]


# ---------------- pivots / bias (D1) ----------------
def test_pivots_are_strict():
    h = np.array([1, 2, 5, 2, 1, 5, 5, 1, 0.0])
    ph, _ = pivot_flags(h, h, 2, 2)
    assert list(np.flatnonzero(ph)) == [2]  # equal highs at 5,6 are not pivots


def test_pivot_usable_only_after_two_right_bars():
    flags = np.zeros(10, dtype=bool)
    flags[4] = True
    assert latest_confirmed(flags, before=6, right=2) == -1  # bars 5 done, 6 not yet
    assert latest_confirmed(flags, before=7, right=2) == 4


def _ds(h: list[float], l: list[float]) -> DailyStructure:  # noqa: E741
    idx = pd.bdate_range("2024-01-01", periods=len(h))
    return DailyStructure(pd.DataFrame({"h": h, "l": l}, index=idx), 2, 2)


def test_bias_bullish_bearish_mixed_equal_insufficient():
    h = [100, 102, 110, 103, 101, 104, 115, 105, 103, 108, 109, 0]
    l = [90, 92, 95, 93, 89, 94, 98, 96, 91, 97, 99, 0]  # noqa: E741
    assert _ds(h, l).bias(11).direction == 1
    neg = _ds([-x for x in l], [-x for x in h]).bias(11)
    assert neg.direction == -1 and neg.reason == "LH+LL"
    mixed = list(l)
    mixed[8] = 88  # lower low with higher high
    assert _ds(h, mixed).bias(11).reason == "mixed_or_equal"
    eqh = list(h)
    eqh[6] = 110  # equal pivot highs -> neutral
    assert _ds(eqh, l).bias(11).direction == 0
    assert _ds(h, l).bias(4).reason == "insufficient_structure"


def test_bias_ignores_pivot_not_yet_confirmed():
    h = [100, 102, 110, 103, 101, 104, 115, 105, 103, 108, 109, 0]
    l = [90, 92, 95, 93, 89, 94, 98, 96, 91, 97, 99, 0]  # noqa: E741
    # at i = 10 the pivot low at k = 8 needs day 10 complete -> not usable; only one pivot low (89) -> insufficient
    assert _ds(h, l).bias(10).reason == "insufficient_structure"


# ---------------- sweep (D2) ----------------
W0, W1 = ns("2024-03-18 10:00"), ns("2024-03-18 11:00")


def test_sweep_requires_strict_beyond_and_close_back_inside():
    c5 = candles(
        [
            ("2024-03-18 09:55", 100, 100, 98, 99.5),  # outside window
            ("2024-03-18 10:00", 100, 100, 99, 99.5),  # low == ref: not beyond
            ("2024-03-18 10:05", 100, 100, 98.9, 99.0),  # close == ref: not back inside
            ("2024-03-18 10:10", 100, 100, 98.8, 99.1),
        ],
        5,
    )
    s = find_sweep(c5, 1, {"PDL": 99.0}, W0, W1)
    assert s is not None and s.idx == 3 and s.extreme == 98.8 and s.ref_name == "PDL"


def test_sweep_short_mirror_and_ref_order():
    c5 = candles([("2024-03-18 10:00", 100, 102, 99, 100.5)], 5)
    s = find_sweep(c5, -1, {"PDH": 101.0, "ASIA_HIGH": 100.8}, W0, W1)
    assert s is not None and s.ref_name == "PDH" and s.extreme == 102


# ---------------- MSS (D3) ----------------
def _c15(highs, lows, closes, start="2024-03-18 08:30"):
    t0 = pd.Timestamp(start)
    rows = [
        ((t0 + pd.Timedelta(minutes=15 * k)).strftime("%Y-%m-%d %H:%M"), c, h, lo, c)
        for k, (h, lo, c) in enumerate(zip(highs, lows, closes, strict=True))
    ]
    return candles(rows, 15)


def test_mss_requires_close_strictly_beyond_confirmed_swing():
    # 08:30..10:45 : swing high 102 at 09:30 (pos 4), confirmed after pos 6 (10:00) completes
    hi = [101, 101.2, 101.3, 101.4, 102.0, 101.0, 100.8, 102.0, 102.4, 103]
    lo = [100] * 10
    cl = [100.5, 100.5, 100.5, 100.5, 101, 100.5, 100.5, 102.0, 102.1, 102.5]
    c15 = _c15(hi, lo, cl)
    ph, pl = pivot_flags(c15.h.to_numpy(), c15.l.to_numpy(), 2, 2)
    m, why = find_mss(c15, ph, pl, 1, ns("2024-03-18 10:05"), W0, W1, 2)
    # 10:00 (pos 6) has no swing usable yet? swing pos 4 needs pos 5,6 complete before candle starts -> not for pos 6
    # pos 6 has no confirmed swing at all -> rejection per R9
    assert m is None and why == "no_confirmed_swing"


def test_mss_first_break_only():
    hi = [101, 101.2, 103, 101.4, 101.3, 101.0, 100.8, 102.0, 103.4, 104]
    lo = [100] * 10
    cl = [100.5, 100.5, 101, 100.5, 101, 100.5, 100.5, 103.0, 103.1, 103.5]
    c15 = _c15(hi, lo, cl)
    ph, pl = pivot_flags(c15.h.to_numpy(), c15.l.to_numpy(), 2, 2)
    m, why = find_mss(c15, ph, pl, 1, ns("2024-03-18 10:05"), W0, W1, 2)
    # swing high 103 at pos 2 (09:00); 10:15 (pos 7) close 103.0 == 103 -> not a break; 10:30 close 103.1 -> MSS
    assert why == "ok" and m is not None and m.idx == 8 and m.swing_price == 103


# ---------------- FVG (D4-D6) ----------------
FVG_ROWS = [
    ("2024-03-18 10:15", 100, 100.5, 99.8, 100.4),  # c1 high 100.5
    ("2024-03-18 10:20", 100.4, 101.5, 100.3, 101.4),  # c2
    ("2024-03-18 10:25", 101.4, 101.8, 100.9, 101.7),  # c3 low 100.9 -> bullish FVG [100.5, 100.9]
    ("2024-03-18 10:30", 101.7, 101.9, 101.4, 101.8),
]  # low 101.4 <= c1 high 101.5: no 2nd FVG


def test_bullish_fvg_on_mss_candle_close_allowed():
    f = find_fvg(candles(FVG_ROWS, 5), 1, ns("2024-03-18 10:30"), W1)
    assert f is not None and (f.bottom, f.top, f.proximal, f.far) == (100.5, 100.9, 100.9, 100.5)


def test_fvg_completed_before_mss_is_excluded():
    assert find_fvg(candles(FVG_ROWS, 5), 1, ns("2024-03-18 10:35"), W1) is None


def test_fvg_requires_contiguous_candles():
    rows = [FVG_ROWS[0], FVG_ROWS[1], ("2024-03-18 10:30", 101.4, 101.8, 100.9, 101.7)]
    assert find_fvg(candles(rows, 5), 1, ns("2024-03-18 10:00"), W1) is None


def test_bearish_fvg_zone():
    rows = [
        ("2024-03-18 10:15", 101, 101.2, 100.6, 100.7),
        ("2024-03-18 10:20", 100.7, 100.8, 99.5, 99.6),
        ("2024-03-18 10:25", 99.6, 100.2, 99.4, 99.5),
    ]
    f = find_fvg(candles(rows, 5), -1, ns("2024-03-18 10:30"), W1)
    assert f is not None and (f.bottom, f.top, f.proximal, f.far) == (100.2, 100.6, 100.2, 100.6)


def test_fvg_after_window_excluded():
    rows = [
        ("2024-03-18 10:50", *FVG_ROWS[0][1:]),
        ("2024-03-18 10:55", *FVG_ROWS[1][1:]),
        ("2024-03-18 11:00", *FVG_ROWS[2][1:]),
    ]
    assert find_fvg(candles(rows, 5), 1, ns("2024-03-18 10:30"), W1) is None


# ---------------- OTE (D7) and premium/discount ----------------
def test_ote_zone_long_short_and_inclusive():
    assert ote_zone(1, 100, 110, 0.62, 0.79) == pytest.approx((102.1, 103.8))
    assert ote_zone(-1, 110, 100, 0.62, 0.79) == pytest.approx((106.2, 107.9))
    from v17.smc_sb.fvg import FVG

    f = FVG(0, 2, 0, 0, 101.0, 103.8, 103.8, 101.0)
    ok, _ = model_b_ok(f, 1, 100, 110, 0.62, 0.79)
    assert ok


def test_premium_discount_strict():
    assert eligible(1, 102.9, 103) and not eligible(1, 103, 103)
    assert eligible(-1, 103.1, 103) and not eligible(-1, 103, 103)
    assert not eligible(1, 1.0, float("nan"))


# ---------------- liquidity / targets (D13) ----------------
def _mk(synth, rows):
    return synth.build(synth.m1_frame(rows))


def test_nwog_friday_close_to_sunday_open(synth):
    rows = [
        ("2024-03-15 16:58", 100, 100, 100, 100.0),
        ("2024-03-15 16:59", 100.5, 100.5, 100.5, 100.5),
        ("2024-03-17 18:00", 102, 102, 102, 102),
        ("2024-03-18 10:00", 102, 102, 102, 102),
    ]
    lo, hi, _ = nwog(_mk(synth, rows), dt.date(2024, 3, 19))
    assert (lo, hi) == (100.5, 102.0)


def test_nwog_zero_width_is_absent(synth):
    rows = [("2024-03-15 16:59", 101, 101, 101, 101.0), ("2024-03-17 18:00", 101, 101, 101, 101)]
    lo, _, _ = nwog(_mk(synth, rows), dt.date(2024, 3, 18))
    assert np.isnan(lo)


def test_target_skips_nearer_level_below_2r_and_touched_levels(synth):
    rows = [(f"2024-03-18 {h:02d}:00", 100, 100.5, 99.5, 100) for h in range(1, 10)]
    mk = _mk(synth, rows)
    start = ns("2024-03-17 17:00")
    # entry 100, stop 99.5 -> 1R = 0.5 + 0.5 = 1.0; NWOG_LO 101 (1.0 < 2R), PDH 103 (3.0 >= 2R)
    lv = DayLevels(103.0, 90.0, float("nan"), float("nan"), 101.0, 101.5, start, start)
    t = select_target(mk, lv, 1, 100.0, 99.5, ns("2024-03-18 10:00"), 2.0, 0.5, 0.0)
    assert t.target is not None and t.target.name == "PDH" and t.target.rr == pytest.approx(3.0)
    # PDH already touched (100.5 high reaches a PDH of 100.4 placed above entry 100.2) -> ineligible -> none
    lv2 = DayLevels(
        100.4, 90.0, float("nan"), float("nan"), float("nan"), float("nan"), start, start
    )
    t2 = select_target(mk, lv2, 1, 100.2, 100.0, ns("2024-03-18 10:00"), 2.0, 0.0, 0.0)
    assert t2.target is None and t2.candidates[0]["touched"] is True


# ---------------- fills and exits (R13-R16) ----------------
def test_fill_gap_through_fills_at_limit_and_expiry_exclusive(synth):
    rows = [
        ("2024-03-18 10:30", 102, 102, 102, 102),
        ("2024-03-18 10:31", 100, 100, 100, 100),
        ("2024-03-18 11:05", 99, 99, 99, 99),
    ]
    mk = _mk(synth, rows)
    assert find_fill(mk, 1, 101.0, ns("2024-03-18 10:30"), ns("2024-03-18 11:05")) == 1
    assert (
        find_fill(mk, 1, 99.5, ns("2024-03-18 10:30"), ns("2024-03-18 11:05")) == -1
    )  # 11:05 bar excluded


def test_stop_first_when_both_touched_in_one_bar(synth):
    rows = [("2024-03-18 10:31", 100, 100, 100, 100), ("2024-03-18 10:32", 100, 106, 94, 100)]
    ex = run_exit(_mk(synth, rows), 1, 0, 95.0, 105.0, ns("2024-03-18 16:00"), 0.5)
    assert ex.reason == "stop" and ex.idx == 1 and ex.price == 94.5


def test_target_not_checked_on_fill_bar(synth):
    rows = [
        ("2024-03-18 10:31", 100, 106, 100, 100),
        ("2024-03-18 10:32", 100, 100, 100, 100),
        ("2024-03-18 15:59", 101, 101, 101, 101),
    ]
    ex = run_exit(_mk(synth, rows), 1, 0, 95.0, 105.0, ns("2024-03-18 16:00"), 0.5)
    assert (
        ex.reason == "force_close_16" and ex.idx == 2 and ex.price == pytest.approx(101 - 0.1 - 0.5)
    )
    assert not ex.data_gap


def test_force_close_flags_missing_1559_bar(synth):
    rows = [("2024-03-18 10:31", 100, 100, 100, 100), ("2024-03-18 15:50", 100, 100, 100, 100)]
    ex = run_exit(_mk(synth, rows), -1, 0, 105.0, 95.0, ns("2024-03-18 16:00"), 0.5)
    assert (
        ex.reason == "force_close_16" and ex.data_gap and ex.price == pytest.approx(100 + 0.1 + 0.5)
    )


def test_short_stop_uses_ask_with_slippage(synth):
    rows = [("2024-03-18 10:31", 100, 100, 100, 100), ("2024-03-18 10:32", 100, 100.95, 100, 100)]
    ex = run_exit(_mk(synth, rows), -1, 0, 101.0, 95.0, ns("2024-03-18 16:00"), 0.5)
    assert ex.reason == "stop" and ex.price == 101.5  # ask high 101.05 >= 101


# ---------------- data guards ----------------
def test_final_exam_locked():
    with pytest.raises(HoldoutAccessError):
        load_m1("NAS100", final_exam=True)


def test_validate_rejects_duplicates_and_crossed_quotes(synth):
    df = synth.m1_frame([("2024-03-18 10:00", 1, 1, 1, 1), ("2024-03-18 10:01", 1, 1, 1, 1)])
    with pytest.raises(DataIntegrityError, match="duplicate"):
        validate_m1(pd.concat([df, df.iloc[[0]]]))
    bad = df.copy()
    bad.loc[0, "ask_c"] = bad.loc[0, "bid_c"] - 0.01
    with pytest.raises(DataIntegrityError, match="crossed"):
        validate_m1(bad)


def test_widen_costs_keeps_mid(synth):
    df = synth.m1_frame([("2024-03-18 10:00", 100, 101, 99, 100.5)])
    w = widen_costs(df, 2.0)
    assert (w.ask_h - w.bid_h).iat[0] == pytest.approx(0.4)
    assert ((w.ask_l + w.bid_l) / 2).iat[0] == pytest.approx(99)


def test_config_validation_and_fingerprint():
    with pytest.raises(ValueError, match="entry_model"):
        StrategyConfig(entry_model="C")
    with pytest.raises(ValueError, match="understate"):
        StrategyConfig(cost_multiplier=0.5)
    assert StrategyConfig().fingerprint() == StrategyConfig().fingerprint()
    assert StrategyConfig().fingerprint() != StrategyConfig(entry_model="B").fingerprint()
