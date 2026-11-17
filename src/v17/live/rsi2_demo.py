"""Pure bar-replay engine for the RSI(2) NAS100 demo poll.

Demo ADR 001 (docs/superpowers/specs/2026-11-17-demo-adr-001-poll-catchup.md):
the poll replays EVERY closed D1 bar newer than the last processed one, in
order, so a missed poll never drops a signal and re-running a poll on the same
day is a no-op. Trade rules mirror ``v17.backtest.rsi2_runner`` exactly:

- Signal at close of bar i if RSI(2)[i] < LONG_THRESHOLD; enter at open[i+1].
- Exit at close of bar j (j >= entry bar) if close[j] > SMA(5)[j].
- Else TIME_CAP exit at close of entry_idx + TIME_CAP_D1.
- No re-entry on the exit bar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from v17.backtest.rsi2_runner import _rsi_wilder, _sma
from v17.setups.rsi2_constants import (
    LONG_THRESHOLD,
    RSI_PERIOD_D1,
    SMA_EXIT_PERIOD_D1,
    TIME_CAP_D1,
)

R_DIST_PCT = 0.01  # 1% of signal close, matches rsi2_runner


@dataclass
class OpenTrade:
    entry_ts: int  # bar open time, unix seconds
    entry_date: str
    entry_price: float
    r_dist: float
    bars_held: int = 0  # closed bars since (and including) the entry bar


@dataclass
class DemoState:
    open_trade: OpenTrade | None = None
    last_processed_ts: int | None = None  # open time of last processed signal bar


@dataclass
class StepResult:
    state: DemoState
    events: list[dict[str, Any]] = field(default_factory=list)  # entry/exit rows for trade_log
    bar_rows: list[dict[str, Any]] = field(default_factory=list)  # one row per processed bar


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def process_bars(
    times: np.ndarray,
    opens: np.ndarray,
    closes: np.ndarray,
    state: DemoState,
    slippage_pts: float,
) -> StepResult:
    """Replay all closed bars newer than ``state.last_processed_ts``.

    ``times/opens/closes`` are full D1 arrays as returned by MT5; the LAST
    element is the current, unfinished bar and is never used as a signal bar.
    If ``state.last_processed_ts`` is None, only the latest closed bar is
    processed (first run, no history to catch up).
    """
    n = len(closes)
    if n < 2:
        raise ValueError("need at least one closed bar plus the current bar")
    rsi = _rsi_wilder(closes, RSI_PERIOD_D1)
    sma5 = _sma(closes, SMA_EXIT_PERIOD_D1)

    last_closed = n - 2
    if state.last_processed_ts is None:
        pending = [last_closed]
    else:
        pending = [i for i in range(last_closed + 1) if int(times[i]) > state.last_processed_ts]

    trade = state.open_trade
    last_ts = state.last_processed_ts
    result = StepResult(state=state)

    for i in pending:
        exited = False
        if trade is not None and int(times[i]) >= trade.entry_ts:
            trade.bars_held += 1
            close_px = float(closes[i])
            reason = None
            if np.isfinite(sma5[i]) and close_px > sma5[i]:
                reason = "SMA_EXIT"
            elif trade.bars_held > TIME_CAP_D1:
                reason = "TIME_CAP"
            if reason is not None:
                pnl_r = (close_px - trade.entry_price) / trade.r_dist if trade.r_dist > 0 else 0.0
                result.events.append({
                    "event": "exit",
                    "exit_date": _date(int(times[i])),
                    "exit_ts": int(times[i]),
                    "exit_price": close_px,
                    "exit_reason": reason,
                    "entry_date": trade.entry_date,
                    "entry_price": trade.entry_price,
                    "bars_held": trade.bars_held,
                    "r_dist": trade.r_dist,
                    "pnl_r": pnl_r,
                })
                trade = None
                exited = True

        entered = False
        if trade is None and not exited and np.isfinite(rsi[i]) and rsi[i] < LONG_THRESHOLD:
            r_dist = max(float(closes[i]) * R_DIST_PCT, 1e-9)
            trade = OpenTrade(
                entry_ts=int(times[i + 1]),
                entry_date=_date(int(times[i + 1])),
                entry_price=float(opens[i + 1]) + slippage_pts,
                r_dist=r_dist,
            )
            result.events.append({
                "event": "entry",
                "signal_date": _date(int(times[i])),
                "signal_ts": int(times[i]),
                "signal_close": float(closes[i]),
                "signal_rsi": float(rsi[i]),
                "entry_date": trade.entry_date,
                "entry_ts": trade.entry_ts,
                "entry_price": trade.entry_price,
                "r_dist": trade.r_dist,
            })
            entered = True

        result.bar_rows.append({
            "signal_date": _date(int(times[i])),
            "signal_close": float(closes[i]),
            "rsi2": float(rsi[i]),
            "sma5": float(sma5[i]),
            "open_trade": None if trade is None else {
                "entry_date": trade.entry_date,
                "entry_price": trade.entry_price,
                "bars_held": trade.bars_held,
            },
            "entry_fired": entered,
            "exit_fired": exited,
        })
        last_ts = int(times[i])

    result.state = DemoState(open_trade=trade, last_processed_ts=last_ts)
    return result


def state_to_json(state: DemoState) -> dict[str, Any]:
    t = state.open_trade
    return {
        "last_processed_ts": state.last_processed_ts,
        "last_processed_date": (
            None if state.last_processed_ts is None else _date(state.last_processed_ts)
        ),
        "open": None if t is None else {
            "entry_ts": t.entry_ts,
            "entry_date": t.entry_date,
            "entry_price": t.entry_price,
            "r_dist": t.r_dist,
            "bars_held": t.bars_held,
        },
    }


def state_from_json(data: dict[str, Any]) -> DemoState:
    raw = data.get("open")
    trade = None
    if raw:
        # Legacy state stored entry_ts_ns (nanoseconds).
        if "entry_ts" in raw:
            entry_ts = int(raw["entry_ts"])
        else:
            entry_ts = int(raw["entry_ts_ns"]) // 1_000_000_000
        trade = OpenTrade(
            entry_ts=entry_ts,
            entry_date=raw["entry_date"],
            entry_price=float(raw["entry_price"]),
            r_dist=float(raw["r_dist"]),
            bars_held=int(raw.get("bars_held", 0)),
        )
    last = data.get("last_processed_ts")
    return DemoState(open_trade=trade, last_processed_ts=None if last is None else int(last))
