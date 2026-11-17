"""Cycle 19 Silver Bullet v4 (full ICT sequence) tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.setups import c17_silver_bullet as sb

SP = sb.SPECS["EURUSD"]


def _build(pre_mon: list, window: list, fri_hi: float = 1.1100, fri_lo: float = 1.0900) -> pd.DataFrame:
    rows, st = [], []
    fri = pd.date_range("2020-01-03 00:00", "2020-01-03 23:59", freq="1min", tz=sb.NY)
    for k, t in enumerate(fri):
        p = 1.1000 + 0.0050 * np.sin(k / 200)
        rows.append((p, p + 0.0001, p - 0.0001, p))
        st.append(t)
    rows[100] = (1.1, fri_hi, 1.0999, 1.1)
    rows[200] = (1.1, 1.1001, fri_lo, 1.1)
    mon = pd.date_range("2020-01-06 00:00", "2020-01-06 12:30", freq="1min", tz=sb.NY, inclusive="left")
    m = list(pre_mon) + list(window)
    m += [window[-1]] * (len(mon) - len(m))
    rows += m
    st += list(mon)
    a = np.array(rows)
    df = pd.DataFrame({"ts_utc": pd.DatetimeIndex(st).tz_convert("UTC").as_unit("ns").asi8})
    for j, k in enumerate("ohlc"):
        df[f"bid_{k}"] = a[:, j] - 0.00001
        df[f"ask_{k}"] = a[:, j] + 0.00001
    return df


def _pre(dip_pdl: bool = True, swing: bool = True) -> list:
    flat = (1.0950, 1.0951, 1.0949, 1.0950)
    pre = [flat] * 600
    if dip_pdl:
        pre[60] = (1.0950, 1.0951, 1.0890, 1.0950)   # PDL 1.0900 taken before the window -> draw = PDH
    if swing:
        pre[590] = (1.0950, 1.0958, 1.0949, 1.0951)  # ICT short-term high 1.0958 (neighbours' highs 1.0951)
    return pre


WIN_OK = [
    (1.0950, 1.0951, 1.0940, 1.0945),   # 10:00 sweep below nearer pool low 1.0949
    (1.0945, 1.0947, 1.0942, 1.0946),   # c1 high 1.0947
    (1.0946, 1.0968, 1.0945, 1.0966),   # c2 displacement, close 1.0966 > 1.0958 -> MSS
    (1.0966, 1.0970, 1.0960, 1.0968),   # c3 low 1.0960 > 1.0947 -> FVG, CE 1.09535 < PD mid 1.1000
    (1.0968, 1.0969, 1.0950, 1.0955),   # retrace -> fill
    (1.0955, 1.1105, 1.0954, 1.1100),   # reaches draw PDH 1.1100
]


def _run(pre, win):
    b = sb.prepare(_build(pre, win))
    days = sb.day_table(b, "AM", "2020-01-06", "2020-01-06")
    return sb.run_slot_v4(b, days, SP, "EURUSD")


def test_full_sequence_long() -> None:
    t = _run(_pre(), WIN_OK)
    r = t.iloc[0]
    assert r.side == 1 and r.tp == pytest.approx(1.1100) and r.entry == pytest.approx((1.0960 + 1.0947) / 2)
    assert r.sl == pytest.approx(1.0940 - SP.buf_min) and r.reason == 2 and r.rr >= 2


def test_no_short_term_high_means_no_mss_no_trade() -> None:
    assert _run(_pre(swing=False), WIN_OK).empty


def test_premium_violation_rejected() -> None:
    # PD midpoint moved below the CE by raising Friday's low range: mid = (1.1100 + 1.0700)/2 = 1.0900 < CE
    b = sb.prepare(_build(_pre(dip_pdl=False), WIN_OK, fri_lo=1.0700))
    days = sb.day_table(b, "AM", "2020-01-06", "2020-01-06")
    assert sb.run_slot_v4(b, days, SP, "EURUSD").empty
