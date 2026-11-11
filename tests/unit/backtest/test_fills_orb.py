"""ORB-cycle fill simulator tests (Task 7).

Covers:
- STOP order triggers and fills with adverse slippage.
- STOP order returns None when never triggered within time_cap_ns.
- Market order applies adverse slippage on entry.
- Market order resolves TP/SL/TIME correctly.
"""
from __future__ import annotations

import pandas as pd

from v17.backtest.fills import simulate_fill_stop, simulate_fill_market


def _bars(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["ts_ns", "open", "high", "low", "close"])


def test_stop_short_triggers_and_adverse_slippage_applied() -> None:
    bars = _bars([
        (0,            100.0, 100.2, 99.8,  100.1),
        (60_000_000_000, 100.5, 101.0, 100.3, 100.9),
        (120_000_000_000, 101.0, 101.5, 100.8, 101.2),
        (180_000_000_000, 101.2, 101.3, 100.4, 100.5),  # TP hit at 100.5
    ])
    res = simulate_fill_stop(
        bars, armed_idx=0, side="short",
        stop_price=100.9, sl=101.3, tp=100.5,
        time_cap_ns=300_000_000_000, slippage_pts=0.1,
    )
    assert res is not None
    assert res["entry_idx"] == 1
    assert abs(res["entry_price"] - (100.9 + 0.1)) < 1e-9
    assert res["exit_reason"] == "TP"
    assert res["exit_price"] == 100.5


def test_stop_returns_none_when_never_triggers() -> None:
    bars = _bars([
        (0,            100.0, 100.2, 99.8, 100.1),
        (60_000_000_000, 100.1, 100.3, 99.9, 100.0),
    ])
    res = simulate_fill_stop(
        bars, armed_idx=0, side="short",
        stop_price=101.0, sl=101.5, tp=100.0,
        time_cap_ns=120_000_000_000, slippage_pts=0.0,
    )
    assert res is None


def test_stop_long_triggers_with_adverse_slippage() -> None:
    bars = _bars([
        (0,            100.0, 100.2, 99.8,  100.1),
        (60_000_000_000, 99.5,  99.6,  99.0,  99.2),   # triggers long stop at 99.3 -> entry 99.3-0.1=99.2
        (120_000_000_000, 99.2, 99.9,  99.1,  99.8),
        (180_000_000_000, 99.8, 100.5, 99.7, 100.4),   # TP at 99.8 hit immediately
    ])
    res = simulate_fill_stop(
        bars, armed_idx=0, side="long",
        stop_price=99.3, sl=98.8, tp=99.8,
        time_cap_ns=300_000_000_000, slippage_pts=0.1,
    )
    assert res is not None
    assert res["entry_idx"] == 1
    assert abs(res["entry_price"] - (99.3 - 0.1)) < 1e-9
    assert res["exit_reason"] == "TP"


def test_market_short_slippage_applied_on_entry() -> None:
    bars = _bars([
        (0,            100.0, 100.1, 99.5,  100.0),
        (60_000_000_000, 99.0,  99.5,  98.0,  98.5),   # SL at 100.5 not hit; TP at 98.0 touched
    ])
    res = simulate_fill_market(
        bars, entry_idx=0, side="short",
        sl=100.5, tp=98.0,
        time_cap_ns=120_000_000_000, slippage_pts=0.5,
    )
    # short at open=100.0 with 0.5 adverse slippage => entry 99.5
    assert abs(res["entry_price"] - 99.5) < 1e-9
    assert res["exit_reason"] == "TP"
    assert res["exit_price"] == 98.0


def test_market_long_slippage_applied_on_entry() -> None:
    bars = _bars([
        (0,            100.0, 100.5, 99.9,  100.3),
        (60_000_000_000, 100.3, 101.5, 100.2, 101.2),   # TP at 101.0 hit
    ])
    res = simulate_fill_market(
        bars, entry_idx=0, side="long",
        sl=99.0, tp=101.0,
        time_cap_ns=120_000_000_000, slippage_pts=0.5,
    )
    # long at open=100.0 with 0.5 adverse slippage => entry 100.5
    assert abs(res["entry_price"] - 100.5) < 1e-9
    assert res["exit_reason"] == "TP"


def test_market_time_cap_forces_exit() -> None:
    bars = _bars([
        (0,            100.0, 100.1, 99.9,  100.0),
        (60_000_000_000, 100.0, 100.1, 99.9, 100.0),
        (120_000_000_000, 100.0, 100.1, 99.9, 100.0),
    ])
    res = simulate_fill_market(
        bars, entry_idx=0, side="short",
        sl=101.0, tp=99.0,
        time_cap_ns=60_000_000_000, slippage_pts=0.0,
    )
    assert res["exit_reason"] == "TIME"
