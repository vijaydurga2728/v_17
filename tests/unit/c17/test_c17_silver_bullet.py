"""Cycle 17 Silver Bullet v2 tests, incl. regressions for the cycle 1 bugs."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.setups import c17_silver_bullet as sb

SP = sb.Spec(buf_min=0.05, buf_max=2.0, fallback=1.0, slip=0.0, commission_rt=0.0)
DAY = "2020-01-06"  # Monday
FLAT = (100.0, 100.1, 99.9, 100.0)


def _m1(window_bars: list[tuple[float, float, float, float]], spread: float = 0.02,
        after: tuple[float, float, float, float] = (100.0, 100.05, 99.95, 100.0)) -> pd.DataFrame:
    """Flat bars 00:00-09:59 NY, then window_bars from 10:00, then `after` bars until 12:30."""
    idx = pd.date_range(f"{DAY} 00:00", f"{DAY} 12:30", freq="1min", tz=sb.NY, inclusive="left")
    n_pre = 600
    rows = [FLAT] * n_pre + list(window_bars)
    rows += [after] * (len(idx) - len(rows))
    a = np.array(rows, dtype=float)
    df = pd.DataFrame({"ts_utc": idx.tz_convert("UTC").as_unit("ns").asi8})
    for j, k in enumerate("ohlc"):
        df[f"bid_{k}"] = a[:, j] - spread / 2
        df[f"ask_{k}"] = a[:, j] + spread / 2
    return df


SWEEP = (99.95, 100.0, 99.5, 99.8)        # 10:00 mid low 99.5 < pool low 99.9 -> LONG day
QUIET = (99.85, 99.9, 99.8, 99.85)
C1 = (99.85, 99.9, 99.8, 99.85)           # high 99.9
C2_BIG = (99.85, 100.65, 99.8, 100.6)     # displacement: range 0.85, body 0.75
C3 = (100.6, 100.62, 100.3, 100.5)        # low 100.3 > C1 high 99.9 -> gap 99.9..100.3, CE 100.1
RETRACE = (100.5, 100.5, 100.05, 100.2)   # ask low 100.06 <= CE -> fill
RALLY = (100.2, 101.3, 100.15, 101.2)     # bid high 101.29 >= TP 101.1


def _run(bars: list, after=(100.0, 100.05, 99.95, 100.0)):
    b = sb.prepare(_m1(bars, after=after))
    days = sb.day_table(b, "AM", DAY, DAY)
    return b, days, sb.run_slot(b, days, SP)


def test_displacement_on_candle_2_found_and_traded() -> None:
    b, days, t = _run([SWEEP, QUIET, C1, C2_BIG, C3, RETRACE, RALLY])
    assert len(t) == 1
    r = t.iloc[0]
    assert r.side == 1 and r.entry == pytest.approx(100.1)
    assert r.sl == pytest.approx(99.5 - 0.05) and r.tp == pytest.approx(101.1)
    assert r.reason == 2 and r.r == pytest.approx((101.1 - 100.1) / 0.65)


def test_regression_big_candle_3_only_is_rejected() -> None:
    c2_small = (99.86, 99.95, 99.85, 99.9)
    c3_big = (99.95, 100.8, 99.94, 100.75)  # gap vs C1 high 99.9 exists, but candle 2 is not displacement
    _, _, t = _run([SWEEP, QUIET, C1, c2_small, c3_big, RETRACE, RALLY])
    assert t.empty


def test_short_side_mirror_and_ask_side_exits() -> None:
    sweep = (100.05, 100.5, 100.0, 100.2)       # high above pool 100.1 -> SHORT day
    c1 = (100.15, 100.2, 100.1, 100.15)         # low 100.1
    c2 = (100.15, 100.2, 99.35, 99.4)           # bearish displacement
    c3 = (99.4, 99.7, 99.38, 99.5)              # high 99.7 < c1 low 100.1 -> gap, CE 99.9
    retrace = (99.5, 99.95, 99.5, 99.8)         # bid high 99.94 >= CE -> fill
    drop = (99.8, 99.85, 98.8, 98.9)            # ask low 98.81 <= TP 98.9
    _, _, t = _run([sweep, (100.15,) * 4, c1, c2, c3, retrace, drop])
    r = t.iloc[0]
    assert r.side == -1 and r.entry == pytest.approx(99.9) and r.tp == pytest.approx(98.9)
    assert r.sl == pytest.approx(100.5 + 0.05) and r.reason == 2


def test_order_expires_without_retrace() -> None:
    away = (100.6, 100.9, 100.5, 100.8)  # never returns to CE 100.1
    b = sb.prepare(_m1([SWEEP, QUIET, C1, C2_BIG, C3] + [away] * 80, after=away))
    days = sb.day_table(b, "AM", DAY, DAY)
    assert sb.run_slot(b, days, SP).empty


def test_both_sides_swept_in_first_bar_skips_day() -> None:
    both = (100.0, 100.5, 99.5, 100.0)
    _, _, t = _run([both, QUIET, C1, C2_BIG, C3, RETRACE, RALLY])
    assert t.empty


def test_stop_first_and_fill_bar_only_checks_sl() -> None:
    crash = (100.2, 101.5, 99.0, 99.2)  # touches TP and SL in one bar -> SL
    _, _, t = _run([SWEEP, QUIET, C1, C2_BIG, C3, RETRACE, crash])
    assert t.iloc[0].reason == 1 and t.iloc[0].r == pytest.approx(-1.0)
    fill_and_tp = (100.5, 101.5, 100.05, 101.2)  # fills and reaches TP in the same bar -> TP ignored there
    _, _, t2 = _run([SWEEP, QUIET, C1, C2_BIG, C3, fill_and_tp, (101.2, 101.25, 101.15, 101.2)])
    assert t2.iloc[0].exit_i > t2.iloc[0].fill_i


def test_time_exit_at_window_end_plus_60() -> None:
    drift = (100.2, 100.3, 100.15, 100.25)
    b, days, t = _run([SWEEP, QUIET, C1, C2_BIG, C3, RETRACE] + [drift] * 140, after=drift)
    r = t.iloc[0]
    assert r.reason == 3 and r.exit_i == int(days.iloc[0].i_hard)
    ts = pd.Timestamp(int(b.ts[r.exit_i]), tz="UTC").tz_convert(sb.NY)
    assert (ts.hour, ts.minute) == (11, 59)


def test_luck_test_runs_and_is_deterministic() -> None:
    b, days, t = _run([SWEEP, QUIET, C1, C2_BIG, C3, RETRACE, RALLY])
    a1 = sb.luck_test(b, days, t, SP, seed=1, n_perms=50)
    a2 = sb.luck_test(b, days, t, SP, seed=1, n_perms=50)
    assert a1 == a2 and 0 < a1["p_mean_r"] <= 1
