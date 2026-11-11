"""ORB FSM transition tests."""
from __future__ import annotations

import pandas as pd

from v17.setups.orb_fsm import ORBFSM, ORBSignal


_MIN = 60_000_000_000


def _bar(ts_min: int, high: float, low: float, close: float, open_: float | None = None) -> pd.Series:
    return pd.Series({
        "ts_ns": ts_min * _MIN,
        "open": open_ if open_ is not None else close,
        "high": high,
        "low": low,
        "close": close,
    })


def _run(fsm: ORBFSM, bars: list[pd.Series]) -> list[ORBSignal]:
    sigs: list[ORBSignal] = []
    for i, b in enumerate(bars):
        s = fsm.on_bar(b, i)
        if s is not None:
            sigs.append(s)
    return sigs


def _fsm(or_start: int = 0, or_end: int = 30, session_end: int = 120) -> ORBFSM:
    return ORBFSM(or_start * _MIN, or_end * _MIN, session_end * _MIN)


def test_or_builds_and_locks() -> None:
    fsm = _fsm()
    bars = [
        _bar(0, 100.5, 99.5, 100.0),   # OR builds
        _bar(15, 100.8, 99.8, 100.2),  # OR continues
        _bar(30, 100.3, 100.0, 100.2), # First bar at OR end — lock
    ]
    sigs = _run(fsm, bars)
    assert sigs == []
    assert fsm.state.or_high == 100.8
    assert fsm.state.or_low == 99.5
    assert fsm.state.phase == "OR_LOCKED"


def test_short_signal_on_upside_breakout_plus_close_back_inside() -> None:
    fsm = _fsm()
    bars = [
        _bar(0, 100.5, 99.5, 100.0),
        _bar(15, 100.8, 99.8, 100.2),
        _bar(30, 100.3, 100.0, 100.2),  # lock OR_high=100.8 OR_low=99.5
        _bar(35, 101.2, 100.5, 101.0),  # breakout (close 101.0 > 100.8)
        _bar(40, 101.1, 100.3, 100.4),  # close back inside at 100.4
    ]
    sigs = _run(fsm, bars)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.side == "short"
    assert s.stop_price == 100.8
    assert s.armed_ns == 40 * _MIN


def test_long_signal_on_downside_breakout_plus_close_back_inside() -> None:
    fsm = _fsm()
    bars = [
        _bar(0, 100.5, 99.5, 100.0),
        _bar(15, 100.8, 99.8, 100.2),
        _bar(30, 100.3, 100.0, 100.2),
        _bar(35, 100.5, 99.0, 99.1),   # breakout down (close 99.1 < 99.5)
        _bar(40, 99.9, 98.8, 99.8),    # close back inside
    ]
    sigs = _run(fsm, bars)
    assert len(sigs) == 1
    assert sigs[0].side == "long"
    assert sigs[0].stop_price == 99.5


def test_no_signal_when_close_back_inside_times_out() -> None:
    fsm = _fsm()
    bars = [
        _bar(0, 100.5, 99.5, 100.0),
        _bar(15, 100.8, 99.8, 100.2),
        _bar(30, 100.3, 100.0, 100.2),
        _bar(35, 101.2, 100.5, 101.0),   # breakout
        _bar(45, 101.5, 100.9, 101.2),   # still outside at 10 min
        _bar(51, 101.6, 101.0, 101.3),   # still outside at 16 min > 15 min cap
    ]
    sigs = _run(fsm, bars)
    assert sigs == []
    assert fsm.state.phase == "EXIT"


def test_only_one_signal_per_day() -> None:
    fsm = _fsm()
    bars = [
        _bar(0, 100.5, 99.5, 100.0),
        _bar(30, 100.3, 100.0, 100.2),   # lock
        _bar(35, 101.2, 100.5, 101.0),   # breakout
        _bar(40, 101.1, 100.3, 100.4),   # close-back-inside -> signal 1
        _bar(45, 101.5, 100.1, 101.3),   # 2nd breakout attempt
        _bar(50, 101.2, 100.2, 100.5),   # 2nd close-back-inside
    ]
    sigs = _run(fsm, bars)
    assert len(sigs) == 1


def test_session_end_forces_exit() -> None:
    fsm = _fsm(session_end=60)
    bars = [
        _bar(0, 100.5, 99.5, 100.0),
        _bar(30, 100.3, 100.0, 100.2),
        _bar(35, 101.2, 100.5, 101.0),   # breakout
        _bar(65, 101.2, 100.2, 100.5),   # past session_end -> EXIT
    ]
    sigs = _run(fsm, bars)
    assert sigs == []
    assert fsm.state.phase == "EXIT"


def test_dead_day_when_no_or_window_bars() -> None:
    fsm = _fsm(or_start=0, or_end=30, session_end=120)
    # First bar comes after OR end — no OR formed.
    bars = [
        _bar(40, 101.0, 100.0, 100.5),
    ]
    sigs = _run(fsm, bars)
    assert sigs == []
    assert fsm.state.phase == "EXIT"
