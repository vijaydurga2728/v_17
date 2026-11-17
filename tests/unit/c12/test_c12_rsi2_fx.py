"""Cycle 12 tests: NY-17:00 bars, parity with the locked cycle 4B runner, short side, luck test."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.backtest.rsi2_runner import run_rsi2_oos_batch
from v17.backtest.walkforward import Fold
from v17.setups import c12_rsi2_fx as c12
from v17.setups.rsi2_engines import RSI2EngineConfig


def _d1(n: int, seed: int, px: float = 1.1, vol: float = 0.006) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    mid = px * np.exp(np.cumsum(rng.normal(0, vol, n)))
    o = np.r_[mid[0], mid[:-1]] * np.exp(rng.normal(0, vol / 5, n))
    days = pd.bdate_range("2016-01-04", periods=n)
    df = pd.DataFrame({"day": days, "ts_utc": days.asi8})
    sp = px * 1e-4
    for k, v in (("o", o), ("h", np.maximum(o, mid) * 1.002), ("l", np.minimum(o, mid) * 0.998), ("c", mid)):
        df[f"bid_{k}"] = v - sp / 2
        df[f"ask_{k}"] = v + sp / 2
    return df


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_parity_with_locked_cycle4b_runner(seed: int) -> None:
    d1 = _d1(900, seed, px=15000.0, vol=0.012)
    p = c12.prepare(d1)
    ws, we = int(d1["ts_utc"].iloc[50]), int(d1["ts_utc"].iloc[850])
    mine = c12.run(p, "L", ws, we, fill="runner")
    logs = run_rsi2_oos_batch(RSI2EngineConfig("x", "USATECHIDXUSD", 1), d1, [Fold(0, 0, 0, ws, we)])
    ref = pd.DataFrame(logs[0].trades)
    assert len(mine) == len(ref) > 10
    np.testing.assert_array_equal(mine["ts_entry_ns"].to_numpy(), ref["ts_entry_ns"].to_numpy())
    np.testing.assert_allclose(mine["pnl_r"].to_numpy(), ref["pnl_r"].to_numpy(), atol=1e-12)


def test_short_side_mirrors_long_on_negated_series() -> None:
    d1 = _d1(600, 7)
    p = c12.prepare(d1)
    ws, we = int(d1["ts_utc"].iloc[20]), int(d1["ts_utc"].iloc[590])
    s = c12.run(p, "S", ws, we)
    assert (s["side"] == -1).any() and (s["side"] == 1).any()
    for _, t in s[s["side"] == -1].head(5).iterrows():
        i, x = int(t.signal_i), int(t.exit_i)
        assert p.rsi[i] > 90
        assert p.mid_c[x] < p.sma[x] or x == i + 1 + 10
        expect = (d1.at[i + 1, "bid_o"] - d1.at[x, "ask_c"]) / (0.01 * p.mid_c[i])
        assert t.pnl_r == pytest.approx(expect)
    long_only = c12.run(p, "L", ws, we)
    assert (long_only["side"] == 1).all()


def test_bidask_costs_reduce_r_vs_mid() -> None:
    d1 = _d1(600, 9)
    p = c12.prepare(d1)
    ws, we = int(d1["ts_utc"].iloc[20]), int(d1["ts_utc"].iloc[590])
    t = c12.run(p, "L", ws, we)
    for _, row in t.head(5).iterrows():
        i, e, x = int(row.signal_i), int(row.entry_i), int(row.exit_i)
        mid_r = (p.mid_c[x] - (d1.at[e, "bid_o"] + d1.at[e, "ask_o"]) / 2) / (0.01 * p.mid_c[i])
        assert row.pnl_r < mid_r


def test_ny_rollover_and_no_weekend_bars() -> None:
    # Sun 17:05 ET -> Mon bar; Fri 16:59 ET -> Fri bar; Mon 17:00 ET -> Tue bar
    stamps = pd.DatetimeIndex(["2020-01-05 17:05", "2020-01-06 09:00", "2020-01-06 17:00",
                               "2020-01-10 16:59"], tz="America/New_York")
    m1 = pd.DataFrame({"ts_utc": stamps.tz_convert("UTC").asi8})
    for k in c12.PX:
        m1[k] = np.arange(4, dtype=float) + (0.1 if k.startswith("ask") else 0.0)
    d = c12.build_fxny_d1(m1)
    assert [str(x.date()) for x in pd.to_datetime(d["day"])] == ["2020-01-06", "2020-01-07", "2020-01-10"]
    assert list(d["n_m1"]) == [2, 1, 1]
    assert d.loc[0, "bid_o"] == 0.0 and d.loc[0, "bid_c"] == 1.0


def test_outcome_table_matches_engine_trades() -> None:
    d1 = _d1(700, 11)
    p = c12.prepare(d1)
    ws, we = int(d1["ts_utc"].iloc[30]), int(d1["ts_utc"].iloc[690])
    t = c12.run(p, "S", ws, we)
    pool = c12.outcome_table(p, ws, we).set_index("signal_i")
    for _, row in t.iterrows():
        col = "r_long" if row.side == 1 else "r_short"
        assert pool.at[int(row.signal_i), col] == pytest.approx(row.pnl_r)


def test_luck_test_counts_and_determinism() -> None:
    d1 = _d1(800, 13)
    p = c12.prepare(d1)
    ws, we = int(d1["ts_utc"].iloc[30]), int(d1["ts_utc"].iloc[790])
    t = c12.run(p, "S", ws, we)
    pool = c12.outcome_table(p, ws, we)
    a = c12.luck_test(t, pool, seed=5, n_perms=300)
    b = c12.luck_test(t, pool, seed=5, n_perms=300)
    assert a == b and a["n_perms"] == 300
    assert a["p_mean_r"] == pytest.approx((a["exceedances"] + 1) / 301)
    assert a["observed_mean_r"] == pytest.approx(float(t["pnl_r"].mean()))


def test_slot_order() -> None:
    s = c12.slots()
    assert len(s) == 14 and s[0] == ("EURUSD", "L") and s[1] == ("EURUSD", "S") and s[13] == ("NZDUSD", "S")


def test_trend_filter_off_by_default_and_blocks_below_sma200() -> None:
    d1 = _d1(900, 21, px=15000.0, vol=0.012)
    p = c12.prepare(d1)
    ws, we = int(d1["ts_utc"].iloc[250]), int(d1["ts_utc"].iloc[890])
    plain = c12.run(p, "L", ws, we)
    filt = c12.run(p, "L", ws, we, trend_filter=True)
    assert len(filt) < len(plain)
    assert all(p.mid_c[i] > p.sma200[i] for i in filt["signal_i"])
    assert any(p.mid_c[i] <= p.sma200[i] for i in plain["signal_i"])
    pool = c12.outcome_table(p, ws, we, trend_only=True)
    assert all(p.mid_c[i] > p.sma200[i] for i in pool["signal_i"])


def test_rsi_buy_and_exit_sma_options() -> None:
    d1 = _d1(900, 31, px=15000.0, vol=0.012)
    p = c12.prepare(d1)
    ws, we = int(d1["ts_utc"].iloc[250]), int(d1["ts_utc"].iloc[890])
    base = c12.run(p, "L", ws, we)
    pd.testing.assert_frame_equal(base, c12.run(p, "L", ws, we, rsi_buy=10.0, exit_sma=5))
    strict = c12.run(p, "L", ws, we, rsi_buy=5.0)
    assert all(p.rsi[i] < 5 for i in strict["signal_i"]) and len(strict) <= len(base)
    slow = c12.run(p, "L", ws, we, exit_sma=10)
    for _, t in slow.iterrows():
        x = int(t.exit_i)
        assert p.mid_c[x] > p.sma10[x] or x == int(t.entry_i) + 10 or p.day_ns[x] >= we
    pool = c12.outcome_table(p, ws, we, exit_sma=10).set_index("signal_i")
    for _, t in slow.iterrows():
        assert pool.at[int(t.signal_i), "r_long"] == pytest.approx(t.pnl_r)
