"""MT5 Python-API connection smoke test.

Verifies credentials in .env successfully initialize the running MT5
terminal and fetches 5 D1 bars for the configured symbol.

The password is NEVER printed. Error messages are scrubbed for the
password substring before any output.

Required .env keys:
  MT5_LOGIN         integer account number
  MT5_PASSWORD      broker password (NEVER echoed)
  MT5_SERVER        server string, e.g. ICMarketsSC-Demo
  MT5_SYMBOL        symbol name (e.g. USTEC)
  MT5_TIMEOUT_MS    optional, defaults to 10000

Exit codes:
  0  success (balance + bars printed)
  1  missing env vars
  2  MetaTrader5 package not installed
  3  mt5.initialize() failed
  4  symbol not selectable
  5  copy_rates returned empty
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _scrub(msg: str, secret: str) -> str:
    if not secret:
        return msg
    return str(msg).replace(secret, "***REDACTED***")


def main() -> int:
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("[mt5-smoke] python-dotenv not installed. Run:")
        print("  .venv\\Scripts\\python.exe -m pip install python-dotenv")
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    env_path = repo_root / ".env"
    if not env_path.exists():
        print(f"[mt5-smoke] missing {env_path}")
        return 1
    load_dotenv(env_path, override=True)

    login_s = os.environ.get("MT5_LOGIN", "")
    password = os.environ.get("MT5_PASSWORD", "")
    server = os.environ.get("MT5_SERVER", "")
    symbol = os.environ.get("MT5_SYMBOL", "")
    timeout_ms = int(os.environ.get("MT5_TIMEOUT_MS", "10000"))

    missing = [k for k, v in {
        "MT5_LOGIN": login_s, "MT5_PASSWORD": password,
        "MT5_SERVER": server, "MT5_SYMBOL": symbol,
    }.items() if not v]
    if missing:
        print(f"[mt5-smoke] missing env keys: {missing}")
        return 1

    try:
        login = int(login_s)
    except ValueError:
        print(f"[mt5-smoke] MT5_LOGIN not an integer: {login_s!r}")
        return 1

    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("[mt5-smoke] MetaTrader5 package not installed. Run:")
        print("  .venv\\Scripts\\python.exe -m pip install MetaTrader5")
        return 2

    print(f"[mt5-smoke] initializing MT5 terminal...", flush=True)
    ok = mt5.initialize(login=login, server=server, password=password, timeout=timeout_ms)
    if not ok:
        err = mt5.last_error()
        print(f"[mt5-smoke] initialize failed: {_scrub(repr(err), password)}")
        mt5.shutdown()
        return 3

    try:
        acct = mt5.account_info()
        if acct is None:
            print("[mt5-smoke] account_info() returned None")
            return 3
        print(f"[mt5-smoke] account: #{acct.login} server={acct.server}")
        print(f"[mt5-smoke] balance={acct.balance:.2f} {acct.currency}  equity={acct.equity:.2f}")
        print(f"[mt5-smoke] trade_mode={acct.trade_mode}  leverage={acct.leverage}")

        if not mt5.symbol_select(symbol, True):
            err = mt5.last_error()
            print(f"[mt5-smoke] symbol_select({symbol!r}) failed: {_scrub(repr(err), password)}")
            return 4
        info = mt5.symbol_info(symbol)
        if info is None:
            print(f"[mt5-smoke] symbol_info({symbol!r}) returned None")
            return 4
        print(f"[mt5-smoke] symbol {symbol}: digits={info.digits} point={info.point} spread={info.spread}")

        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 5)
        if rates is None or len(rates) == 0:
            err = mt5.last_error()
            print(f"[mt5-smoke] copy_rates returned empty: {_scrub(repr(err), password)}")
            return 5

        print(f"[mt5-smoke] last 5 D1 bars for {symbol}:")
        import datetime as _dt
        for r in rates:
            ts = _dt.datetime.fromtimestamp(int(r["time"]), _dt.UTC).strftime("%Y-%m-%d")
            print(f"  {ts}  O={r['open']:.2f}  H={r['high']:.2f}  L={r['low']:.2f}  C={r['close']:.2f}  V={int(r['tick_volume'])}")

        print("[mt5-smoke] OK")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
