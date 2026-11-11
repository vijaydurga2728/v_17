"""ORB engine_runner unit test — crafted M1 reversal scenario."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import pytz

from v17.backtest.engine_runner import run_engine_oos_batch
from v17.backtest.walkforward import Fold
from v17.setups.orb_engines import ORB_CATALOG


_NY = pytz.timezone("America/New_York")


def _bid_ask_bars_for_crafted_day() -> pd.DataFrame:
    """Build 90 M1 bars 09:28 → 10:58 NY on 2020-06-15.

    Scenario:
      - OR window 09:30-10:00 forms OR_high=100.5, OR_low=99.5.
      - 10:03 bar closes at 100.8 (breakout up).
      - 10:08 bar closes at 100.4 (back inside OR -> short signal, stop=100.5).
      - After fill, price drifts down; TP at 0.5R = 100.5 - 0.25 = ~100.25
        (SL = 100.5 + 0.5 * ATR; ATR_14 on crafted data stable around ~0.2
        so SL ≈ 100.6, r_dist ≈ 0.1, tp ≈ 100.4).
    """
    rows = []
    base_ny = pd.Timestamp("2020-06-15 09:28", tz=_NY)
    # Build 90 minutes of M1 bars.
    for i in range(90):
        t_utc = base_ny + pd.Timedelta(minutes=i)
        t_utc = t_utc.tz_convert("UTC")
        ts_ns = t_utc.value

        # Phase A (09:28-10:00): OR builds between 99.5 and 100.5.
        if i < 32:
            mid_close = 100.0 + (i % 4) * 0.1  # oscillate
            bid_c = mid_close - 0.0005
            ask_c = mid_close + 0.0005
            hi = mid_close + 0.05
            lo = mid_close - 0.05
        # Phase B (10:00-10:03): breakout above 100.5
        elif i < 35:
            mid_close = 100.6 + (i - 32) * 0.1  # 100.6, 100.7, 100.8
            bid_c = mid_close - 0.0005
            ask_c = mid_close + 0.0005
            hi = mid_close + 0.1
            lo = mid_close - 0.1
        # Phase C (10:03-10:08): drift back below 100.5
        elif i < 40:
            mid_close = 100.8 - (i - 34) * 0.1  # 100.7, 100.6, 100.5, 100.4, 100.3
            bid_c = mid_close - 0.0005
            ask_c = mid_close + 0.0005
            hi = mid_close + 0.1
            lo = mid_close - 0.1
        # Phase D (post-signal): price falls to TP
        else:
            mid_close = max(100.2 - (i - 40) * 0.01, 99.8)
            bid_c = mid_close - 0.0005
            ask_c = mid_close + 0.0005
            hi = mid_close + 0.05
            lo = mid_close - 0.05

        rows.append({
            "ts_utc": ts_ns,
            "symbol": "USATECHIDXUSD",
            "bid_o": bid_c, "bid_h": hi - 0.0005, "bid_l": lo - 0.0005, "bid_c": bid_c,
            "ask_o": ask_c, "ask_h": hi + 0.0005, "ask_l": lo + 0.0005, "ask_c": ask_c,
            "bid_volume": 10.0, "ask_volume": 10.0, "spread_mid": 0.001,
        })
    return pd.DataFrame(rows)


def test_runner_emits_short_trade_on_crafted_reversal() -> None:
    bars = _bid_ask_bars_for_crafted_day()
    engine = ORB_CATALOG[0]
    oos_start = pd.Timestamp("2020-06-15", tz="UTC").value
    oos_end = pd.Timestamp("2020-06-16", tz="UTC").value
    fold = Fold(fold_id=99, train_start=0, train_end=oos_start - 1,
                oos_start=oos_start, oos_end=oos_end)
    calendar = pd.DataFrame(columns=["timestamp_utc", "currency", "impact"])

    logs = run_engine_oos_batch(engine, bars, calendar, [fold])
    assert len(logs) == 1
    tl = logs[0]
    assert tl.engine_id == "ORB-NAS100"
    assert tl.fold_id == 99
    assert len(tl.trades) == 1
    t = tl.trades[0]
    assert t["side"] == "short"
    assert t["exit_reason"] in ("TP", "SL", "TIME")
    assert t["symbol"] == "USATECHIDXUSD"


def test_runner_empty_bars_returns_empty_logs() -> None:
    engine = ORB_CATALOG[0]
    fold = Fold(fold_id=1, train_start=0, train_end=0, oos_start=0, oos_end=1)
    calendar = pd.DataFrame(columns=["timestamp_utc", "currency", "impact"])
    logs = run_engine_oos_batch(engine, pd.DataFrame(), calendar, [fold])
    assert len(logs) == 1
    assert logs[0].trades == []
