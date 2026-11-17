"""Cycle 15 IBS engine tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.setups import c15_ibs as c15


def _bars(rows: list[tuple[float, float, float, float]], spread: float = 1.0) -> pd.DataFrame:
    days = pd.bdate_range("2020-01-06", periods=len(rows))
    df = pd.DataFrame({"day": days})
    for k, col in zip("ohlc", range(4), strict=True):
        v = np.array([r[col] for r in rows], dtype=float)
        df[f"bid_{k}"] = v - spread / 2
        df[f"ask_{k}"] = v + spread / 2
    return df


def _rand(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = 1000 + np.cumsum(rng.normal(0, 10, n))
    o = c + rng.normal(0, 3, n)
    h = np.maximum(o, c) + rng.random(n) * 8
    lo = np.minimum(o, c) - rng.random(n) * 8
    return _bars(list(zip(o, h, lo, c, strict=True)))


W = (0, 2**62)


def test_ibs_value_and_flat_bar() -> None:
    p = c15.prepare(_bars([(100, 110, 100, 101), (100, 100, 100, 100)]))
    assert p.ibs[0] == pytest.approx(0.1) and np.isnan(p.ibs[1])


def test_long_next_close_fills() -> None:
    rows = [(100, 110, 100, 100.5),     # IBS 0.05 -> long signal
            (101, 106, 99, 105),        # entry at open, exit at this close
            (105, 106, 104, 105)]
    p = c15.prepare(_bars(rows))
    t = c15.run(p, c15.Setting(0.1, 0.9, "next_close"), *W)
    assert list(t.side) == [1] and list(t.exit_i) == [1]
    assert t.pnl_r[0] == pytest.approx(((105 - 0.5) - (101 + 0.5)) / (0.01 * 100.5))


def test_short_ibs_cross_exit_and_cap() -> None:
    rows = [(100, 110, 100, 109.5),     # IBS 0.95 -> short
            (109, 112, 100, 111),       # IBS 0.92 no cross
            (110, 111, 100, 100.5),     # IBS 0.045 < 0.1 -> cross, exit here
            (100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100)]
    p = c15.prepare(_bars(rows))
    t = c15.run(p, c15.Setting(0.1, 0.9, "ibs_cross"), *W)
    assert t.iloc[0].side == -1 and t.iloc[0].exit_i == 2
    assert t.iloc[0].pnl_r == pytest.approx(((109 - 0.5) - (100.5 + 0.5)) / (0.01 * 109.5))
    # cap: no cross within 5 bars -> exit at entry + 4
    rows2 = [(100, 110, 100, 109.5)] + [(100, 101, 99, 100)] * 7
    t2 = c15.run(c15.prepare(_bars(rows2)), c15.Setting(0.1, 0.9, "ibs_cross"), *W)
    assert t2.iloc[0].exit_i == 1 + 4


def test_signal_on_exit_bar_allowed() -> None:
    rows = [(100, 110, 100, 100.5), (101, 110, 100, 100.2), (100, 106, 99, 105), (105, 106, 104, 105)]
    t = c15.run(c15.prepare(_bars(rows)), c15.Setting(0.1, 0.9, "next_close"), *W)
    assert list(t.signal_i) == [0, 1] and list(t.entry_i) == [1, 2]


@pytest.mark.parametrize("setting", c15.MENU)
def test_outcome_table_matches_engine(setting: c15.Setting) -> None:
    p = c15.prepare(_rand(400, 3))
    t = c15.run(p, setting, *W)
    pool = c15.outcome_table(p, setting, *W).set_index("signal_i")
    assert len(t) > 20 and (t.side == 1).any() and (t.side == -1).any()
    for _, row in t.iterrows():
        col = "r_long" if row.side == 1 else "r_short"
        assert pool.at[int(row.signal_i), col] == pytest.approx(row.pnl_r)


def test_no_lookahead() -> None:
    d = _rand(300, 5)
    p = c15.prepare(d)
    s = c15.Setting(0.2, 0.8, "ibs_cross")
    sig_a = [c15.signal(p, i, s) for i in range(150)]
    d2 = d.copy()
    d2.loc[150:, ["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]] += 500.0
    p2 = c15.prepare(d2)
    assert sig_a == [c15.signal(p2, i, s) for i in range(150)]
