"""RSI(2) forward paper test poll (USTEC + US500) — paper trading only, no live orders.

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
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.live.rsi2_demo import DemoState, process_bars, state_from_json, state_to_json
from v17.setups.rsi2_constants import RSI_PERIOD_D1, SMA_EXIT_PERIOD_D1

# Forward paper test (docs/superpowers/specs/2026-11-17-c14-forward-paper-test.md):
# symbol -> fixed cost per fill in points (~broker spread on 2026-11-17: 0.9 and 0.3).
FORWARD_SYMBOLS = {"USTEC": 1.0, "US500": 0.5}
STALE_RETRIES = 10
STALE_RETRY_SLEEP_S = 3.0
MAX_CURRENT_BAR_AGE_S = 4 * 86_400  # covers Fri bar seen on Sun/Mon morning


def _scrub(msg: str, secret: str) -> str:
    if not secret:
        return msg
    return str(msg).replace(secret, "***REDACTED***")


def _save_state(state_path: Path, state: DemoState) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state_to_json(state), indent=2), encoding="utf-8")
    tmp.replace(state_path)  # atomic: a crash never leaves half-written state


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
    if not all([login_s, password, server]):
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
        out_root = repo / "out" / "forward_c14"
        codes = {sym: _poll_symbol(mt5, sym, slip, out_root / sym) for sym, slip in FORWARD_SYMBOLS.items()}
        print(f"[demo-poll] results {codes}", flush=True)
        if any(codes.values()):
            return max(codes.values())
        (out_root / "last_poll.txt").write_text(datetime.now(UTC).isoformat(), encoding="utf-8")
        print("[demo-poll] OK", flush=True)
        return 0
    finally:
        mt5.shutdown()


def _poll_symbol(mt5, symbol: str, slippage_pts: float, out_dir: Path) -> int:  # type: ignore[no-untyped-def]
    """Process one market. Returns 0 on success, else an error code (5 insufficient, 6 stale)."""
    # First request after attach can return cached (stale) history while the
    # terminal syncs. Retry until the current D1 bar is recent; fail loudly
    # (exit 6) otherwise so the watchdog alerts instead of logging a no-op.
    mt5.symbol_select(symbol, True)
    rates = None
    fresh = False
    for _attempt in range(STALE_RETRIES):
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 400)
        if rates is not None and len(rates) > 0:
            age_s = datetime.now(UTC).timestamp() - int(rates[-1]["time"])
            if age_s < MAX_CURRENT_BAR_AGE_S:
                fresh = True
                break
        time.sleep(STALE_RETRY_SLEEP_S)
    if rates is None or len(rates) < max(RSI_PERIOD_D1 + 2, SMA_EXIT_PERIOD_D1 + 1):
        print(f"[demo-poll] {symbol}: insufficient bars")
        return 5
    if not fresh:
        last = datetime.fromtimestamp(int(rates[-1]["time"]), UTC).date()
        print(f"[demo-poll] {symbol}: STALE history: current bar {last}")
        return 6

    # The last bar in copy_rates_from_pos with start=0 is the CURRENT (unfinished) bar.
    # process_bars only uses fully-closed bars as signal bars and replays every
    # closed bar newer than state.last_processed_ts (demo ADR 001).
    times = np.array([int(r["time"]) for r in rates], dtype=np.int64)
    opens = np.array([float(r["open"]) for r in rates])
    closes = np.array([float(r["close"]) for r in rates])

    state_path = out_dir / "state.json"
    trade_log = out_dir / "trade_log.jsonl"
    equity_log = out_dir / "equity_curve.jsonl"
    state = (
        state_from_json(json.loads(state_path.read_text(encoding="utf-8")))
        if state_path.exists() else DemoState()
    )
    res = process_bars(times, opens, closes, state, slippage_pts=slippage_pts)
    for ev in res.events:
        _append_jsonl(trade_log, {"symbol": symbol, **ev})
        print(f"[demo-poll] {symbol} {ev['event'].upper()} {ev}", flush=True)
    poll_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for row in res.bar_rows:
        print(f"[demo-poll] {symbol} bar {row['signal_date']} close={row['signal_close']:.2f} "
              f"RSI(2)={row['rsi2']:.2f} SMA(5)={row['sma5']:.2f}", flush=True)
        _append_jsonl(equity_log, {"poll_date_utc": poll_utc, "symbol": symbol, **row})
    if not res.bar_rows:
        print(f"[demo-poll] {symbol}: no new closed bars since last poll", flush=True)
    _save_state(state_path, res.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
