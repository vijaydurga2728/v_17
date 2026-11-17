"""Cycle 10 rule tests (pre-reg §11.1)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.setups import c10_intraday_momentum as c10
from v17.setups.c10_intraday_momentum import (
    I_1000,
    I_1530_ENTRY,
    I_1530_SIG,
    I_LAST,
    N_MIN,
    DayGrid,
)
from v17.validation.c10_mcpt import run_mcpt, slot_seed

SPREAD = 1.0


def make_grid(mid_c: np.ndarray, mid_o: np.ndarray | None = None, vol: float = 1.0,
              prev_ok: np.ndarray | None = None) -> DayGrid:
    """mid_c/mid_o: (D, 390). h/l = max/min(o, c) ± 0.5. bid/ask = mid ∓ SPREAD/2."""
    d = mid_c.shape[0]
    mid_o = mid_c.copy() if mid_o is None else mid_o
    mid_h = np.maximum(mid_o, mid_c) + 0.5
    mid_l = np.minimum(mid_o, mid_c) - 0.5
    px = {}
    for k, m in zip("ohlc", (mid_o, mid_h, mid_l, mid_c), strict=True):
        px[f"mid_{k}"] = m
        px[f"bid_{k}"] = m - SPREAD / 2
        px[f"ask_{k}"] = m + SPREAD / 2
    px["vol"] = np.full((d, N_MIN), vol)
    dates = c10.full_rth_days("2020-01-01", "2020-12-31")[:d]
    ok = np.r_[False, np.ones(d - 1, bool)] if prev_ok is None else prev_ok
    return DayGrid(dates, ok, px)


def flat_days(n: int, px: float = 1000.0, day_move: float = 10.0) -> np.ndarray:
    """n days; each day opens at px and drifts linearly to px + day_move by 15:59."""
    return np.tile(px + np.linspace(0, day_move, N_MIN), (n, 1))


# ------------------------------------------------------------- grid builder
def _m1(date: str, start: str = "09:00", end: str = "16:30") -> pd.DataFrame:
    idx = pd.date_range(f"{date} {start}", f"{date} {end}", freq="1min", tz="America/New_York",
                        inclusive="left")
    mid = 1000 + np.arange(len(idx), dtype=float)
    df = pd.DataFrame({"ts_utc": idx.tz_convert("UTC").asi8})
    for k in "ohlc":
        df[f"bid_{k}"] = mid - 0.5
        df[f"ask_{k}"] = mid + 0.5
    df["bid_volume"] = 1.0
    df["ask_volume"] = 2.0
    return df


@pytest.mark.parametrize("date", ["2020-01-15", "2020-07-15"])
def test_grid_maps_0930_to_0_and_1559_to_389(date: str) -> None:
    g = c10.build_grid(_m1(date), date, date)
    assert g.n_days == 1
    first_rth = 30.0 + 1000  # 09:30 is the 31st minute from 09:00
    assert g["mid_c"][0, 0] == first_rth and g["mid_c"][0, I_LAST] == first_rth + 389
    assert g["vol"][0, 0] == 3.0
    assert np.isfinite(g["mid_c"]).all()          # 16:00+ bars never enter the grid


def test_grid_excludes_half_days() -> None:
    assert c10.build_grid(_m1("2019-11-29"), "2019-11-29", "2019-11-29").n_days == 0


# --------------------------------------------------------------- G and B
def test_g_signal_uses_price_at_1000_vs_prev_close_and_fills() -> None:
    c = flat_days(20)
    c[-1] = 1000.0
    c[-1, I_1000] = 1011.0             # 10:00 price above PC (=1010) -> long
    c[-1, I_1000 + 1:] = 1009.0        # rest of day below PC: B would be short
    c[-1, I_LAST] = 1020.0
    g = make_grid(c)
    tg = c10.run_slot(g, "G")
    k = int(np.flatnonzero(tg.day == 19)[0])
    assert tg.side[k] == 1
    entry = g["ask_o"][19, I_1530_ENTRY]
    ru = c10.r_unit_frac(g)[19]
    assert tg.r[k] == pytest.approx((g["bid_c"][19, I_LAST] - entry) / (entry * ru))
    tb = c10.run_slot(g, "B")
    assert tb.side[tb.day == 19].tolist() == [-1]   # price at 15:30 (1009) < PC


def test_b_signal_bar_is_1529_close() -> None:
    c = flat_days(20)
    c[-1] = 1009.0
    c[-1, I_1530_SIG] = 1011.0         # only the 15:29 close is above PC
    g = make_grid(c)
    tb = c10.run_slot(g, "B")
    assert tb.side[tb.day == 19].tolist() == [1]


def test_zero_signal_and_missing_bars_skip() -> None:
    c = flat_days(20)
    c[-1, I_1000] = 1010.0             # exactly PC -> no trade
    g = make_grid(c)
    assert 19 not in c10.run_slot(g, "G").day
    g2 = make_grid(flat_days(20))
    g2.px["ask_o"][19, I_1530_ENTRY] = np.nan
    assert 19 not in c10.run_slot(g2, "G").day


def test_no_prev_close_no_trade() -> None:
    ok = np.r_[False, np.ones(19, bool)]
    ok[19] = False
    g = make_grid(flat_days(20), prev_ok=ok)
    assert 19 not in c10.run_slot(g, "G").day


def test_r_unit_warmup_and_value() -> None:
    g = make_grid(flat_days(20))
    ru = c10.r_unit_frac(g)
    assert np.isnan(ru[:14]).all() and np.isfinite(ru[14:]).all()
    assert ru[14] == pytest.approx(10.0 / 1000.0)        # |C/O - 1| = 10/1000 every day
    tr = c10.run_slot(g, "G")
    assert tr.day.min() >= 14


def test_no_lookahead_signal_and_r_unit() -> None:
    base = make_grid(flat_days(20))
    t0 = c10.run_slot(base, "G")
    c = flat_days(20)
    c[19, I_1530_ENTRY:] += 50.0       # change only post-entry prices on the last day
    g = make_grid(c)
    t1 = c10.run_slot(g, "G")
    np.testing.assert_array_equal(t0.side, t1.side)
    np.testing.assert_array_equal(c10.r_unit_frac(base), c10.r_unit_frac(g))
    sig_a, sig_b = c10.sigma_open(base), c10.sigma_open(g)
    np.testing.assert_array_equal(sig_a[:20], sig_b[:20])   # sigma(D) uses only days < D


def test_slippage_adverse_both_sides() -> None:
    g = make_grid(flat_days(20))
    t0, t1 = c10.run_slot(g, "G", 0.0), c10.run_slot(g, "G", 1.0)
    assert (t1.r_long < t0.r_long).all() and (t1.r_short < t0.r_short).all()


# --------------------------------------------------------------------- Z
def test_sigma_and_vwap_construction() -> None:
    c = flat_days(16)
    g = make_grid(c)
    s = c10.sigma_open(g)
    m = 100
    expect = abs(c[0, m] / c[0, 0] - 1)
    assert np.isnan(s[12, m]) and s[13, m] == pytest.approx(expect) and s[15, m] == pytest.approx(expect)
    vw = c10.vwap(g)
    tp = (g["mid_h"][0, :3] + g["mid_l"][0, :3] + g["mid_c"][0, :3]) / 3
    assert vw[0, 2] == pytest.approx(tp.mean())


def test_z_state_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    g = make_grid(flat_days(3))
    sig = np.zeros((3, 12), dtype=np.int64)
    sig[0] = [0, 1, 1, 0, -1, -1, 1, 0, 0, 0, 0, 1]
    monkeypatch.setattr(c10, "z_signals", lambda _g: sig)
    monkeypatch.setattr(c10, "z_tradeable_days", lambda _g: np.array([True, False, False]))
    monkeypatch.setattr(c10, "r_unit_frac", lambda _g: np.full(3, 0.01))
    tr = c10.run_z(g)
    chk = [i + 1 for i in c10.Z_CHECKS]
    got = list(zip(tr.side.tolist(), tr.entry_i.tolist(), tr.exit_i.tolist(), strict=True))
    assert got == [
        (1, chk[1], chk[3]),     # open long, hold, close on 0
        (-1, chk[4], chk[6]),    # open short, hold, reverse ...
        (1, chk[6], chk[7]),     # ... into long at the same open, close on 0
        (1, chk[11], N_MIN),     # last check opens long, closed at 15:59 close
    ]
    assert np.isfinite(tr.r).all()


def test_z_signal_needs_band_and_vwap() -> None:
    n = 16
    c = flat_days(n, day_move=2.0)
    c[-1, :] = 1000.0
    c[-1, 59:] = 1100.0                      # breaks far above UB from the 10:29 bar on
    g = make_grid(c, mid_o=np.tile(c[:, :1], (1, N_MIN)))
    sig = c10.z_signals(g)
    assert sig[-1, 0] == 0 and sig[-1, 1] == 1


# -------------------------------------------------------------------- MCPT
def test_mcpt_preserves_long_count_and_formula() -> None:
    g = make_grid(flat_days(60))
    tr = c10.run_slot(g, "G")
    res, log = run_mcpt(tr, "G", n_perms=200)
    assert res.n_perms == 200 and len(log) == 200
    assert (log["n_long"] == int((tr.side == 1).sum())).all()
    assert res.observed_mean_r == pytest.approx(float(tr.r.mean()))
    assert res.p_value == pytest.approx((res.exceedances + 1) / 201)
    assert (log["seed"] == slot_seed("G")).all() and slot_seed("Z") == 20261117002
    res2, log2 = run_mcpt(tr, "G", n_perms=200)
    assert res2 == res and log2.equals(log)


def test_mcpt_direction_skill_detected_and_absent() -> None:
    rng = np.random.default_rng(0)
    n = 400
    side = rng.choice([-1, 1], n)
    move = rng.normal(0, 1, n)
    skilled = c10.TradeArrays(np.arange(n), side, np.zeros(n, int), np.zeros(n, int),
                              r_long=side * np.abs(move), r_short=-side * np.abs(move))
    assert run_mcpt(skilled, "G", n_perms=500)[0].p_value < 0.01
    noskill = c10.TradeArrays(np.arange(n), side, np.zeros(n, int), np.zeros(n, int),
                              r_long=move, r_short=-move)
    assert run_mcpt(noskill, "G", n_perms=500)[0].p_value > 0.01
