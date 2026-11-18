"""Cycle 20 Silver Bullet v5 unit tests: SMT logic and IPDA levels."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.setups import c17_silver_bullet as base
from v17.setups import c20_silver_bullet_v5 as v5


def _partner(window_low: float, window_high: float) -> base.Bars:
    """Partner flat 100 (99.9-100.1) 00:00-09:59 NY on 2020-01-06, then window bars with given extremes."""
    idx = pd.date_range("2020-01-06 00:00", "2020-01-06 10:30", freq="1min", tz=base.NY, inclusive="left")
    rows = [(100.0, 100.1, 99.9, 100.0)] * 600 + [(100.0, window_high, window_low, 100.0)] * (len(idx) - 600)
    a = np.array(rows)
    df = pd.DataFrame({"ts_utc": idx.tz_convert("UTC").as_unit("ns").asi8})
    for j, k in enumerate("ohlc"):
        df[f"bid_{k}"] = a[:, j]
        df[f"ask_{k}"] = a[:, j]
    return base.prepare(df)


T_DAY, T_PH, T_WS = v5._bounds_ns(pd.Timestamp("2020-01-06"), "AM")
T_SWEEP = T_WS + 5 * 60_000_000_000


@pytest.mark.parametrize(("rel", "side", "lo", "hi", "expect"), [
    (1, 1, 99.95, 100.05, True),    # positive partner, LONG: partner holds its low -> SMT
    (1, 1, 99.80, 100.05, False),   # partner also made a new low -> no SMT
    (-1, 1, 99.80, 100.05, True),   # inverse partner (DXY), LONG: DXY no new high -> SMT (its low is irrelevant)
    (-1, 1, 99.95, 100.20, False),  # DXY made a new high -> no SMT
    (1, -1, 99.95, 100.20, False),  # positive partner, SHORT: partner made new high -> no SMT
    (-1, -1, 99.95, 100.20, True),  # inverse partner, SHORT: DXY no new low -> SMT
])
def test_smt_ok(rel: int, side: int, lo: float, hi: float, expect: bool) -> None:
    assert v5.smt_ok(_partner(lo, hi), rel, side, T_DAY, T_PH, T_WS, T_SWEEP) is expect


def test_smt_missing_partner_data_is_false() -> None:
    pb = _partner(99.95, 100.05)
    later = T_WS + 24 * 3600 * 1_000_000_000
    assert v5.smt_ok(pb, 1, 1, later, later, later + 1, later + 2) is False


def test_ipda_levels_use_only_prior_days() -> None:
    days = pd.bdate_range("2020-01-01", periods=70)
    rows, st = [], []
    for k, d in enumerate(days):
        for m in range(0, 1440, 60):
            p = 100.0 + k
            rows.append((p, p + 0.5, p - 0.5, p))
            st.append(pd.Timestamp(d).tz_localize(base.NY) + pd.Timedelta(minutes=m))
    a = np.array(rows)
    df = pd.DataFrame({"ts_utc": pd.DatetimeIndex(st).tz_convert("UTC").as_unit("ns").asi8})
    for j, k in enumerate("ohlc"):
        df[f"bid_{k}"] = a[:, j]
        df[f"ask_{k}"] = a[:, j]
    lv = v5.ipda_levels(base.prepare(df))
    d = days[65]
    assert lv.loc[d, "h20"] == pytest.approx(100 + 64 + 0.5)        # highest of the previous 20 days
    assert lv.loc[d, "l60"] == pytest.approx(100 + 5 - 0.5)         # lowest of the previous 60 days
    assert np.isnan(lv.loc[days[10], "h20"])
    assert lv.loc[d, "mid20"] == pytest.approx(((164.5) + (145 - 0.5)) / 2)
