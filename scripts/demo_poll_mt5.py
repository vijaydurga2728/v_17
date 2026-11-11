"""30-day RSI(2) demo poll — paper trading only, no live orders.

Spec: docs/superpowers/specs/2026-11-11-30day-demo-scaffolding.md
Strategy: RSI2-USATECHIDXUSD at commit 1465ef3.

Run this script once per weekday after NY cash close. It reads the latest
D1 bars from MT5, decides enter/exit per Connors RSI(2) long-only rules,
and appends to local JSONL logs. It never places a real order.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.backtest.rsi2_runner import _rsi_wilder, _sma
from v17.setups.rsi2_constants import (
    LONG_THRESHOLD,
    RSI_PERIOD_D1,
    SMA_EXIT_PERIOD_D1,
    TIME_CAP_D1,
)


SLIPPAGE_PTS = 1.0  # confirmed live spread from smoke test
R_DIST_PCT = 0.01   # 1% of entry price, matches RSI(2) runner convention


@dataclass
class OpenTrade:
    entry_ts_ns: int
    entry_date: str
    entry_price: float
    r_dist: float
    bars_held: int = 0


def _scrub(msg: str, secret: str) -> str:
    if not secret:
        return msg
    return str(msg).replace(secret, "***REDACTED***")


def _load_state(state_path: Path) -> OpenTrade | None:
    if not state_path.exists():
        return None
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if not data.get("open"):
        return None
    t = data["open"]
    return OpenTrade(
        entry_ts_ns=int(t["entry_ts_ns"]),
        entry_date=t["entry_date"],
        entry_price=float(t["entry_price"]),
        r_dist=float(t["r_dist"]),
        bars_held=int(t.get("bars_held", 0)),
    )


def _save_state(state_path: Path, trade: OpenTrade | None) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if trade is None:
        state_path.write_text(json.dumps({"open": None}, indent=2), encoding="utf-8")
    else:
        state_path.write_text(json.dumps({"open": {
            "entry_ts_ns": trade.entry_ts_ns,
            "entry_date": trade.entry_date,
            "entry_price": trade.entry_price,
            "r_dist": trade.r_dist,
            "bars_held": trade.bars_held,
        }}, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def main() -> int:
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("[demo-poll] python-dotenv missing"); return 2
    repo = Path(__file__).resolve().parents[1]
    load_dotenv(repo / ".env", override=True)

    login_s = os.environ.get("MT5_LOGIN", "")
    password = os.environ.get("MT5_PASSWORD", "")
    server = os.environ.get("MT5_SERVER", "")
    symbol = os.environ.get("MT5_SYMBOL", "")
    if not all([login_s, password, server, symbol]):
        print("[demo-poll] missing .env keys"); return 1

    try:
        login = int(login_s)
    except ValueError:
        print("[demo-poll] MT5_LOGIN not integer"); return 1

    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("[demo-poll] MetaTrader5 package missing"); return 2

    ok = mt5.initialize(login=login, server=server, password=password, timeout=10000)
    if not ok:
        err = mt5.last_error()
        print(f"[demo-poll] init failed: {_scrub(repr(err), password)}")
        mt5.shutdown()
        return 3

    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 400)
        if rates is None or len(rates) < max(RSI_PERIOD_D1 + 2, SMA_EXIT_PERIOD_D1 + 1):
            print(f"[demo-poll] insufficient bars"); return 5

        times = np.array([int(r["time"]) for r in rates])
        opens = np.array([float(r["open"]) for r in rates])
        highs = np.array([float(r["high"]) for r in rates])
        lows = np.array([float(r["low"]) for r in rates])
        closes = np.array([float(r["close"]) for r in rates])

        # The last bar in copy_rates_from_pos with start=0 is the CURRENT (unfinished) bar.
        # We only act on the previous bar (last fully-closed one).
        idx_signal = len(closes) - 2
        idx_next_open = len(closes) - 1

        signal_ts = int(times[idx_signal])
        signal_date = datetime.fromtimestamp(signal_ts, timezone.utc).strftime("%Y-%m-%d")
        print(f"[demo-poll] signal bar date={signal_date} close={closes[idx_signal]:.2f}", flush=True)

        rsi = _rsi_wilder(closes, RSI_PERIOD_D1)
        sma5 = _sma(closes, SMA_EXIT_PERIOD_D1)
        rsi_signal = float(rsi[idx_signal])
        sma_signal = float(sma5[idx_signal])
        print(f"[demo-poll] RSI(2)={rsi_signal:.2f}  SMA(5)={sma_signal:.2f}", flush=True)

        state_path = repo / "out" / "demo" / "state.json"
        trade_log = repo / "out" / "demo" / "trade_log.jsonl"
        equity_log = repo / "out" / "demo" / "equity_curve.jsonl"

        trade = _load_state(state_path)

        # Exit logic for open trade.
        exit_fired = False
        if trade is not None:
            trade.bars_held += 1
            close_px = float(closes[idx_signal])
            exit_reason = None
            if np.isfinite(sma_signal) and close_px > sma_signal:
                exit_reason = "SMA_EXIT"
            elif trade.bars_held >= TIME_CAP_D1:
                exit_reason = "TIME_CAP"
            if exit_reason is not None:
                exit_price = close_px
                pnl_abs = exit_price - trade.entry_price
                pnl_r = pnl_abs / trade.r_dist if trade.r_dist > 0 else 0.0
                row = {
                    "event": "exit",
                    "exit_date": signal_date,
                    "exit_ts_ns": signal_ts,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "entry_date": trade.entry_date,
                    "entry_price": trade.entry_price,
                    "bars_held": trade.bars_held,
                    "r_dist": trade.r_dist,
                    "pnl_r": pnl_r,
                }
                _append_jsonl(trade_log, row)
                print(f"[demo-poll] EXIT {exit_reason} price={exit_price:.2f} pnl_r={pnl_r:+.3f}", flush=True)
                trade = None
                exit_fired = True

        # Entry logic (only if no open trade and not exited this poll).
        entry_fired = False
        if trade is None and not exit_fired and np.isfinite(rsi_signal) and rsi_signal < LONG_THRESHOLD:
            entry_price = float(opens[idx_next_open]) + SLIPPAGE_PTS
            r_dist = max(float(closes[idx_signal]) * R_DIST_PCT, 1e-9)
            trade = OpenTrade(
                entry_ts_ns=int(times[idx_next_open]),
                entry_date=datetime.fromtimestamp(int(times[idx_next_open]), timezone.utc).strftime("%Y-%m-%d"),
                entry_price=entry_price,
                r_dist=r_dist,
                bars_held=0,
            )
            row = {
                "event": "entry",
                "signal_date": signal_date,
                "signal_ts_ns": signal_ts,
                "signal_close": closes[idx_signal],
                "signal_rsi": rsi_signal,
                "entry_date": trade.entry_date,
                "entry_ts_ns": trade.entry_ts_ns,
                "entry_price": trade.entry_price,
                "r_dist": trade.r_dist,
            }
            _append_jsonl(trade_log, row)
            print(f"[demo-poll] ENTRY price={entry_price:.2f} r_dist={r_dist:.2f}", flush=True)
            entry_fired = True

        _save_state(state_path, trade)

        # Append equity curve line.
        poll_row = {
            "poll_date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "signal_date": signal_date,
            "signal_close": float(closes[idx_signal]),
            "rsi2": rsi_signal,
            "sma5": sma_signal,
            "open_trade": None if trade is None else {
                "entry_date": trade.entry_date, "entry_price": trade.entry_price,
                "bars_held": trade.bars_held,
            },
            "entry_fired_this_poll": entry_fired,
            "exit_fired_this_poll": exit_fired,
        }
        _append_jsonl(equity_log, poll_row)
        (repo / "out" / "demo" / "last_poll.txt").write_text(
            datetime.now(timezone.utc).isoformat(), encoding="utf-8",
        )
        print(f"[demo-poll] OK", flush=True)
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
