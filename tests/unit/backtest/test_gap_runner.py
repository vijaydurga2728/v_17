"""Overnight gap-fade runner tests."""
from __future__ import annotations

import pandas as pd
import pytz

from v17.backtest.gap_runner import run_gap_oos_batch
from v17.backtest.walkforward import Fold
from v17.setups.gap_engines import GAP_CATALOG


_NY = pytz.timezone("America/New_York")


def _build_two_days() -> pd.DataFrame:
    """Day 1 close 100.0; day 2 open 101.0 (1% gap-up).

    Day 2 session fades: price drifts from 101.0 down to 100.4 by close.
    Expect: short entry at 101.0, TP at 100.5 (0.5 * 1.0 gap = 0.5 R), exit_reason TP.
    """
    rows = []

    def add_bar(ts_ns, bid_c, ask_c, hi_add=0.05, lo_sub=0.05):
        rows.append({
            "ts_utc": ts_ns, "symbol": "USATECHIDXUSD",
            "bid_o": bid_c, "bid_h": bid_c + hi_add, "bid_l": bid_c - lo_sub, "bid_c": bid_c,
            "ask_o": ask_c, "ask_h": ask_c + hi_add, "ask_l": ask_c - lo_sub, "ask_c": ask_c,
            "bid_volume": 10.0, "ask_volume": 10.0, "spread_mid": 0.01,
        })

    # Day 1: 09:30 -> 16:00 NY on 2020-06-15. Steady at 15000.0 (realistic NAS100 scale).
    d1_open = pd.Timestamp("2020-06-15 09:30", tz=_NY).tz_convert("UTC")
    for m in range(390):
        t = (d1_open + pd.Timedelta(minutes=m)).value
        add_bar(t, 15000.0 - 0.1, 15000.0 + 0.1, hi_add=5.0, lo_sub=5.0)

    # Day 2: 09:30 open at 15150.0 (1% gap-up), drifts to 15075.
    d2_open = pd.Timestamp("2020-06-16 09:30", tz=_NY).tz_convert("UTC")
    for m in range(390):
        t = (d2_open + pd.Timedelta(minutes=m)).value
        mid_c = max(15150.0 - m * (75.0 / 390), 15075.0)
        add_bar(t, mid_c - 0.1, mid_c + 0.1, hi_add=5.0, lo_sub=5.0)

    return pd.DataFrame(rows)


def test_short_fade_on_gap_up_hits_tp() -> None:
    bars = _build_two_days()
    engine = GAP_CATALOG[0]
    oos_start = pd.Timestamp("2020-06-15", tz="UTC").value
    oos_end = pd.Timestamp("2020-06-17", tz="UTC").value
    fold = Fold(fold_id=1, train_start=0, train_end=oos_start - 1,
                oos_start=oos_start, oos_end=oos_end)

    logs = run_gap_oos_batch(engine, bars, [fold])
    assert len(logs) == 1
    trades = logs[0].trades
    assert len(trades) == 1
    t = trades[0]
    assert t["side"] == "short"
    assert abs(t["gap_pct"] - 0.01) < 1e-6
    assert t["exit_reason"] == "TP"
    assert t["pnl_r"] > 0.4


def test_tiny_gap_is_skipped() -> None:
    """Gap below GAP_MIN_PCT (0.30%) is filtered out."""
    rows = []
    _NY = pytz.timezone("America/New_York")

    def add_bar(ts_ns, mid):
        rows.append({
            "ts_utc": ts_ns, "symbol": "USATECHIDXUSD",
            "bid_o": mid - 0.0005, "bid_h": mid + 0.05, "bid_l": mid - 0.05, "bid_c": mid - 0.0005,
            "ask_o": mid + 0.0005, "ask_h": mid + 0.05, "ask_l": mid - 0.05, "ask_c": mid + 0.0005,
            "bid_volume": 10.0, "ask_volume": 10.0, "spread_mid": 0.01,
        })

    # Day 1 close 15000, day 2 open 15015 (0.1% gap — below 0.3% floor).
    d1_open = pd.Timestamp("2020-06-15 09:30", tz=_NY).tz_convert("UTC")
    for m in range(390):
        add_bar((d1_open + pd.Timedelta(minutes=m)).value, 15000.0)
    d2_open = pd.Timestamp("2020-06-16 09:30", tz=_NY).tz_convert("UTC")
    for m in range(390):
        add_bar((d2_open + pd.Timedelta(minutes=m)).value, 15015.0)
    bars = pd.DataFrame(rows)

    engine = GAP_CATALOG[0]
    oos_start = pd.Timestamp("2020-06-15", tz="UTC").value
    oos_end = pd.Timestamp("2020-06-17", tz="UTC").value
    fold = Fold(fold_id=1, train_start=0, train_end=oos_start - 1,
                oos_start=oos_start, oos_end=oos_end)

    logs = run_gap_oos_batch(engine, bars, [fold])
    assert logs[0].trades == []
