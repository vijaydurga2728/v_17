"""Cycle 18 Silver Bullet v3 (ICT's own rules) tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.setups import c17_silver_bullet as sb

SP = sb.SPECS["EURUSD"]


def _two_days(window: list[tuple[float, float, float, float]], pre_px: float = 1.1030) -> pd.DataFrame:
    """Fri 2020-01-03 range 1.0900-1.1100 (PDH/PDL); Mon 2020-01-06 flat at pre_px, then `window` from 10:00."""
    rows, stamps = [], []
    fri = pd.date_range("2020-01-03 00:00", "2020-01-03 23:59", freq="1min", tz=sb.NY)
    for k, t in enumerate(fri):
        p = 1.1000 + 0.0090 * np.sin(k / 200)
        rows.append((p, p + 0.0001, p - 0.0001, p))
        stamps.append(t)
    rows[100] = (1.1, 1.1100, 1.0999, 1.1)
    rows[200] = (1.1, 1.1001, 1.0900, 1.1)
    mon = pd.date_range("2020-01-06 00:00", "2020-01-06 12:30", freq="1min", tz=sb.NY, inclusive="left")
    flat = (pre_px, pre_px + 0.0001, pre_px - 0.0001, pre_px)
    mrows = [flat] * 600 + window
    mrows += [window[-1]] * (len(mon) - len(mrows))
    rows += mrows
    stamps += list(mon)
    a = np.array(rows)
    df = pd.DataFrame({"ts_utc": pd.DatetimeIndex(stamps).tz_convert("UTC").as_unit("ns").asi8})
    for j, k in enumerate("ohlc"):
        df[f"bid_{k}"] = a[:, j] - 0.00001
        df[f"ask_{k}"] = a[:, j] + 0.00001
    return df


def test_levels_and_long_toward_nearer_pdh() -> None:
    w = [(1.1030, 1.1032, 1.1028, 1.1031),       # c1 high 1.1032
         (1.1031, 1.1045, 1.1030, 1.1044),
         (1.1044, 1.1046, 1.1040, 1.1045),       # c3 low 1.1040 > 1.1032 -> bullish FVG, CE 1.1036
         (1.1045, 1.1046, 1.1035, 1.1038),       # retrace -> fill
         (1.1038, 1.1105, 1.1037, 1.1102)]       # reaches PDH 1.1100
    b = sb.prepare(_two_days(w))
    lv = sb.daily_levels(b)
    assert lv.loc[pd.Timestamp("2020-01-06"), "pdh"] == pytest.approx(1.1100)
    days = sb.day_table(b, "AM", "2020-01-06", "2020-01-06")
    t = sb.run_slot_v3(b, days, SP, "EURUSD")
    r = t.iloc[0]
    assert r.side == 1 and r.entry == pytest.approx(1.1036) and r.tp == pytest.approx(1.1100)
    assert r.sl == pytest.approx(1.1028 - SP.buf_min) and r.reason == 2


def test_min_frame_blocks_close_draw() -> None:
    w = [(1.1090, 1.1092, 1.1088, 1.1091), (1.1091, 1.1096, 1.1090, 1.1095),
         (1.1095, 1.1097, 1.1094, 1.1096), (1.1096, 1.1097, 1.1093, 1.1094)]
    b = sb.prepare(_two_days(w, pre_px=1.1090))  # PDH 1.1100 only ~7 pips from CE < 15 pips
    days = sb.day_table(b, "AM", "2020-01-06", "2020-01-06")
    assert sb.run_slot_v3(b, days, SP, "EURUSD").empty


def test_short_when_pdl_is_nearer() -> None:
    w = [(1.0960, 1.0962, 1.0958, 1.0959),       # c1 low 1.0958
         (1.0959, 1.0960, 1.0945, 1.0946),
         (1.0946, 1.0950, 1.0944, 1.0945),       # c3 high 1.0950 < 1.0958 -> bearish FVG, CE 1.0954
         (1.0945, 1.0956, 1.0944, 1.0952),       # retrace -> fill
         (1.0952, 1.0953, 1.0895, 1.0898)]       # reaches PDL 1.0900
    b = sb.prepare(_two_days(w, pre_px=1.0960))
    days = sb.day_table(b, "AM", "2020-01-06", "2020-01-06")
    r = sb.run_slot_v3(b, days, SP, "EURUSD").iloc[0]
    assert r.side == -1 and r.tp == pytest.approx(1.0900) and r.reason == 2
