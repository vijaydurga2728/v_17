"""Demo ADR 001: poll catch-up, idempotency, and backtest parity."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.backtest.rsi2_runner import run_rsi2_oos_batch
from v17.backtest.walkforward import Fold
from v17.live.rsi2_demo import (
    DemoState,
    OpenTrade,
    process_bars,
    state_from_json,
    state_to_json,
)
from v17.setups.rsi2_constants import COST_SLIPPAGE_PTS_USATECH, TIME_CAP_D1
from v17.setups.rsi2_engines import RSI2_CATALOG

DAY = 86_400


def _series(n: int, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    closes = 15_000 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
    opens = np.r_[closes[0], closes[:-1]] * np.exp(rng.normal(0, 0.002, n))
    times = 1_600_000_000 + DAY * np.arange(n, dtype=np.int64)
    return times, opens, closes


def _backtest_trades(times, opens, closes) -> list[tuple[int, int, str, float]]:
    df = pd.DataFrame({
        "ts_utc": times * 1_000_000_000,
        "bid_o": opens, "ask_o": opens, "bid_h": np.maximum(opens, closes),
        "ask_h": np.maximum(opens, closes), "bid_l": np.minimum(opens, closes),
        "ask_l": np.minimum(opens, closes), "bid_c": closes, "ask_c": closes,
    })
    fold = Fold(fold_id=0, train_start=0, train_end=0, oos_start=0, oos_end=2**62)
    logs = run_rsi2_oos_batch(RSI2_CATALOG[0], df, [fold])
    return [
        (t["ts_entry_ns"] // 1_000_000_000, t["ts_exit_ns"] // 1_000_000_000, t["exit_reason"], t["pnl_r"])
        for t in logs[0].trades
    ]


def _run_polls(times, opens, closes, poll_ends: list[int]) -> list[dict]:
    """Each poll sees bars[0..end] where bar `end` is the unfinished current bar."""
    state = DemoState(last_processed_ts=int(times[4]))  # runner starts scanning at i=5
    events: list[dict] = []
    for end in poll_ends:
        res = process_bars(times[: end + 1], opens[: end + 1], closes[: end + 1], state,
                           slippage_pts=COST_SLIPPAGE_PTS_USATECH)
        events += res.events
        state = state_from_json(state_to_json(res.state))  # round-trip through disk format
    return events


def _demo_trades(events: list[dict]) -> list[tuple[int, int, str, float]]:
    entries = [e for e in events if e["event"] == "entry"]
    exits = [e for e in events if e["event"] == "exit"]
    return [(en["entry_ts"], ex["exit_ts"], ex["exit_reason"], ex["pnl_r"]) for en, ex in zip(entries, exits, strict=False)]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_catchup_with_gaps_and_repeats_matches_backtest(seed: int) -> None:
    n = 700
    times, opens, closes = _series(n, seed)
    rng = np.random.default_rng(seed + 100)
    # Polls: mostly daily, with multi-day gaps and same-day repeats.
    ends: list[int] = []
    cur = 6
    while cur < n - 1:
        ends.append(cur)
        if rng.random() < 0.2:
            ends.append(cur)  # duplicate poll same day
        cur += int(rng.choice([1, 1, 1, 2, 4, 7]))
    ends.append(n - 1)

    demo = _demo_trades(_run_polls(times, opens, closes, ends))
    # Backtest sees the same closed bars (exclude the final unfinished bar).
    bt = _backtest_trades(times[:-1], opens[:-1], closes[:-1])
    # Drop backtest trades whose exit was forced by the end of data.
    horizon = int(times[n - 2 - TIME_CAP_D1 - 1])
    bt = [t for t in bt if t[1] <= horizon]
    demo = [t for t in demo if t[1] <= horizon]

    assert len(bt) > 10
    assert [t[:3] for t in demo] == [t[:3] for t in bt]
    assert np.allclose([t[3] for t in demo], [t[3] for t in bt])


def test_time_cap_exits_at_entry_plus_cap() -> None:
    # Monotone decline: close never exceeds SMA(5) -> only TIME_CAP can exit.
    n = 40
    closes = 20_000 - 50.0 * np.arange(n)
    opens = closes + 10
    times = 1_600_000_000 + DAY * np.arange(n, dtype=np.int64)
    state = DemoState(open_trade=OpenTrade(entry_ts=int(times[10]), entry_date="x",
                                           entry_price=float(opens[10]), r_dist=200.0),
                      last_processed_ts=int(times[9]))
    res = process_bars(times, opens, closes, state, slippage_pts=0.0)
    first_exit = next(e for e in res.events if e["event"] == "exit")
    assert first_exit["exit_reason"] == "TIME_CAP"
    assert first_exit["exit_ts"] == int(times[10 + TIME_CAP_D1])


def test_repeat_poll_is_noop() -> None:
    times, opens, closes = _series(200, 7)
    state = DemoState(last_processed_ts=int(times[100]))
    first = process_bars(times, opens, closes, state, slippage_pts=1.0)
    again = process_bars(times, opens, closes, first.state, slippage_pts=1.0)
    assert again.events == [] and again.bar_rows == []
    assert state_to_json(again.state) == state_to_json(first.state)


def test_first_run_processes_only_latest_closed_bar() -> None:
    times, opens, closes = _series(50, 9)
    res = process_bars(times, opens, closes, DemoState(), slippage_pts=1.0)
    assert len(res.bar_rows) == 1
    assert res.state.last_processed_ts == int(times[-2])


def test_legacy_state_migrates() -> None:
    legacy = {"open": {"entry_ts_ns": 1_700_000_000 * 10**9, "entry_date": "2023-11-14",
                       "entry_price": 15000.0, "r_dist": 150.0, "bars_held": 2}}
    st = state_from_json(legacy)
    assert st.open_trade is not None and st.open_trade.entry_ts == 1_700_000_000
    assert st.last_processed_ts is None
    assert state_from_json({"open": None}).open_trade is None
