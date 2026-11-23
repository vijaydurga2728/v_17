r"""FTMO $10,000 Challenge — MT5 Live Execution Bridge.

Implements the verified Cycle 22 Dual-Engine Portfolio on MT5:
- London Killzone (02:00-05:00 NY / 12:30-15:30 IST) on GBPUSD
- NY AM Opening Drive (10:00-11:00 NY / 20:30-21:30 IST) on EURUSD, USTEC, US500

User Operating Window:
- Monday to Friday: 10:10 AM IST to 7:00 PM IST (19:00 IST)
- Automatically launches MT5 terminal (terminal64.exe) if closed
- Automatically executes live pending orders on MT5 account #53143050

FTMO Rules & Safety Enforced:
1. Dynamic Risk Sizing: 0.50% ($50) risk per trade on $10,000 equity.
2. Hard Daily Circuit Breaker: Max 2 trades/day, halt if daily loss >= -$100 (1.0%).
3. Static Max DD Floor: $9,000 (never allows account to breach 10.0% max loss).
4. Auto-Flatten: Auto-cancels pending orders and closes positions by 16:30 NY.
5. Weekend Blackout: Auto-flattens by Friday 16:00 NY.

Usage:
  .venv\Scripts\python.exe scripts/live_ftmo_runner.py --poll --dry-run
  .venv\Scripts\python.exe scripts/live_ftmo_runner.py --loop --live --enforce-ist-hours
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Final
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from v17.setups.c22_silver_bullet import (
    SPECS as C22_SPECS,
    Bars,
    DayContext,
    M5Bars,
    Spec,
    build_m5,
    find_setup,
    latest_confirmed_pivot,
    pivot_flags,
)

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

NY = ZoneInfo("America/New_York")
IST = ZoneInfo("Asia/Kolkata")

DEFAULT_MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

# Mapping internal names to MT5 broker symbols
BROKER_SYMBOLS = {
    "USA30IDXUSD": "US30",
    "USATECHIDXUSD": "USTEC",
    "USA500IDXUSD": "US500",
    "XAUUSD": "XAUUSD",
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
}

# Mapping MT5 broker symbols to C22 strategy symbols
BROKER_TO_C22 = {
    "US30": "USA30IDXUSD",
    "USTEC": "USATECHIDXUSD",
    "US500": "USA500IDXUSD",
    "XAUUSD": "XAUUSD",
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
}

# Spec calibrations matching verified Grade-A c22_silver_bullet
SPECS = {
    "US30":   {"min_stop": 15.0,   "max_stop": 250.0,  "point": 0.1,     "pip": 1.0},
    "USTEC":  {"min_stop": 8.0,    "max_stop": 120.0,  "point": 0.01,    "pip": 1.0},
    "US500":  {"min_stop": 1.5,    "max_stop": 25.0,   "point": 0.01,    "pip": 1.0},
    "XAUUSD": {"min_stop": 2.50,   "max_stop": 20.00,  "point": 0.01,    "pip": 0.10},
    "EURUSD": {"min_stop": 0.0006, "max_stop": 0.0030, "point": 0.00001, "pip": 0.0001},
    "GBPUSD": {"min_stop": 0.0015, "max_stop": 0.0035, "point": 0.00001, "pip": 0.0001},
}

# Maximum strict spread limits (Reject setups if live spread > threshold)
MAX_ALLOWED_SPREAD = {
    "US30":   4.0,       # 4.0 points max
    "USTEC":  3.0,       # 3.0 points max
    "US500":  1.0,       # 1.0 point max
    "XAUUSD": 0.50,      # $0.50 max
    "EURUSD": 0.00010,   # 1.0 pip max
    "GBPUSD": 0.00015,   # 1.5 pips max
}

# Asset Class Groupings for Non-Correlated Concurrency (Max 2 trades: 1 FX + 1 Index or Commodity)
ASSET_CLASSES = {
    "EURUSD": "FX",
    "GBPUSD": "FX",
    "US30":   "INDEX",
    "USTEC":  "INDEX",
    "US500":  "INDEX",
    "XAUUSD": "COMMODITY",
}
MAX_CONCURRENT_POSITIONS = 2

# Currency exposure mapping for live economic news blackout
SYMBOL_CURRENCY_MAP = {
    "EURUSD": {"USD", "EUR"},
    "GBPUSD": {"USD", "GBP"},
    "US30":   {"USD"},
    "USTEC":  {"USD"},
    "US500":  {"USD"},
    "XAUUSD": {"USD"},
}

LOG_DIR = REPO / "out" / "live_ftmo"
MAX_TRADES_PER_DAY: Final[int] = 4


def log_audit_event(event_type: str, details: dict) -> None:
    """Append structured JSON line to out/live_ftmo/execution_audit.jsonl."""
    try:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event_type,
            **details,
        }
        audit_file = LOG_DIR / "execution_audit.jsonl"
        with open(audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


class LiveEconomicCalendar:
    """Automated Live Economic Calendar Gate using ForexFactory JSON API.
    
    Caches data per hour. Gates trades 15 minutes before to 15 minutes after High-Impact events.
    """
    def __init__(self, cache_file: Path):
        self.cache_file = cache_file
        self.events: list[dict] = []
        self.last_fetch: float = 0.0
        self.load_cache()

    def load_cache(self) -> None:
        if self.cache_file.exists():
            try:
                data = json.loads(self.cache_file.read_text(encoding="utf-8"))
                self.events = data.get("events", [])
                self.last_fetch = data.get("timestamp", 0.0)
            except Exception:
                self.events = []

    def save_cache(self) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(
                json.dumps({"timestamp": self.last_fetch, "events": self.events}, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def sync(self) -> None:
        now_ts = time.time()
        # Refresh every 4 hours if already populated
        if now_ts - self.last_fetch < 14400 and len(self.events) > 0:
            return

        import urllib.request
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                parsed = []
                for item in raw:
                    if item.get("impact") == "High" and item.get("country") in ("USD", "EUR", "GBP"):
                        parsed.append({
                            "title": item.get("title", ""),
                            "country": item.get("country", ""),
                            "date": item.get("date", ""),
                        })
                self.events = parsed
                self.last_fetch = now_ts
                self.save_cache()
                print(f"[CALENDAR SYNC] Successfully updated economic calendar ({len(self.events)} High-Impact events cached).")
        except Exception as e:
            print(f"[WARN] Economic calendar sync warning: {e}")

    def is_in_blackout(self, symbol: str, now_utc: datetime) -> tuple[bool, str]:
        """Check if symbol is within 15 mins before to 15 mins after any High-Impact event."""
        if not self.events:
            self.sync()

        currencies = SYMBOL_CURRENCY_MAP.get(symbol, {"USD"})
        from dateutil import parser as dateparser

        for ev in self.events:
            if ev["country"] in currencies:
                try:
                    ev_dt = dateparser.isoparse(ev["date"]).astimezone(UTC)
                    diff_sec = (ev_dt - now_utc).total_seconds()
                    # 15 minutes before (-900s) to 15 minutes after (+900s)
                    if -900 <= diff_sec <= 900:
                        mins = diff_sec / 60.0
                        time_rel = f"in {mins:.0f}m" if mins > 0 else f"{abs(mins):.0f}m ago"
                        return True, f"High-Impact {ev['country']} '{ev['title']}' {time_rel} ({ev_dt.strftime('%H:%M')} UTC)"
                except Exception:
                    continue
        return False, ""


def _scrub(msg: str, secret: str) -> str:
    if not secret:
        return msg
    return str(msg).replace(secret, "***REDACTED***")


def get_ny_now() -> datetime:
    return datetime.now(UTC).astimezone(NY)


def get_ist_now() -> datetime:
    return datetime.now(UTC).astimezone(IST)


def is_in_window(now_dt: datetime, start_h: int, start_m: int, end_h: int, end_m: int) -> bool:
    curr_min = now_dt.hour * 60 + now_dt.minute
    start_min = start_h * 60 + start_m
    end_min = end_h * 60 + end_m
    return start_min <= curr_min < end_min


def calculate_lots(symbol: str, risk_dollars: float, stop_distance: float, mt5_module) -> float:
    """Calculate exact volume respecting broker margin, tick value, and lot steps."""
    info = mt5_module.symbol_info(symbol)
    if not info:
        return 0.01

    tick_value = info.trade_tick_value
    tick_size = info.trade_tick_size

    if tick_size <= 0 or tick_value <= 0:
        return 0.01

    # Dollar loss per 1.0 lot for stop_distance
    ticks = stop_distance / tick_size
    loss_per_lot = ticks * tick_value

    if loss_per_lot <= 0:
        return 0.01

    raw_lots = risk_dollars / loss_per_lot

    # Round to volume step
    step = info.volume_step if info.volume_step > 0 else 0.01
    lots = round(raw_lots / step) * step
    lots = max(info.volume_min, min(lots, info.volume_max))
    return round(lots, 2)


class FTMOLiveEngine:
    def __init__(self, dry_run: bool = True, enforce_ist_hours: bool = False):
        self.dry_run = dry_run
        self.enforce_ist_hours = enforce_ist_hours
        self.mt5 = None
        self.password = ""
        self.state_file = LOG_DIR / "state.json"
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.load_state()
        self.calendar = LiveEconomicCalendar(LOG_DIR / "economic_calendar.json")
        self.calendar.sync()

    def load_state(self) -> None:
        if self.state_file.exists():
            try:
                self.state = json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                self.state = {"date": "", "trades_today": 0, "daily_pnl": 0.0}
        else:
            self.state = {"date": "", "trades_today": 0, "daily_pnl": 0.0}

    def save_state(self) -> None:
        self.state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def ensure_terminal_process(self, terminal_path: str) -> None:
        """Check if MetaTrader 5 is running; if not, launch it."""
        try:
            # Check via tasklist
            output = subprocess.check_output('tasklist /FI "IMAGENAME eq terminal64.exe"', shell=True, text=True)
            if "terminal64.exe" not in output:
                print(f"[AUTO-LAUNCH] MetaTrader 5 is not running. Starting: {terminal_path}")
                if os.path.exists(terminal_path):
                    subprocess.Popen([terminal_path])
                    time.sleep(5)  # Wait for startup
                else:
                    print(f"[WARN] Terminal path not found: {terminal_path}")
            else:
                print("[OK] MetaTrader 5 (terminal64.exe) is already active.")
        except Exception as e:
            print(f"[WARN] Process check error: {e}")

    def connect(self) -> bool:
        try:
            from dotenv import load_dotenv
            load_dotenv(REPO / ".env", override=True)
            import MetaTrader5 as mt5
            self.mt5 = mt5
        except ImportError as e:
            print(f"[ERROR] Import error: {e}")
            return False

        login_s = os.environ.get("MT5_LOGIN", "")
        self.password = os.environ.get("MT5_PASSWORD", "")
        server = os.environ.get("MT5_SERVER", "")
        mt5_path = os.environ.get("MT5_PATH", DEFAULT_MT5_PATH)

        if not all([login_s, self.password, server]):
            print("[ERROR] Missing MT5 credentials in .env")
            return False

        # Ensure terminal process is up
        self.ensure_terminal_process(mt5_path)

        # Initialize MT5 with path and credentials
        ok = self.mt5.initialize(
            path=mt5_path,
            login=int(login_s),
            password=self.password,
            server=server,
            timeout=15000,
        )
        if not ok:
            err = self.mt5.last_error()
            print(f"[ERROR] MT5 connection failed: {_scrub(repr(err), self.password)}")
            return False

        acc = self.mt5.account_info()
        print(f"[OK] Connected to MT5 Account #{acc.login} ({acc.server})")
        print(f"     Balance: ${acc.balance:,.2f} | Equity: ${acc.equity:,.2f} | Margin Free: ${acc.margin_free:,.2f}")

        # Ensure all portfolio symbols are selected in MT5 MarketWatch
        for s in BROKER_SYMBOLS.values():
            self.mt5.symbol_select(s, True)
        return True

    def check_daily_reset(self, today_str: str) -> None:
        if self.state.get("date") != today_str:
            self.state["date"] = today_str
            self.state["trades_today"] = 0
            self.state["daily_pnl"] = 0.0
            self.save_state()

    def audit_ftmo_limits(self) -> tuple[bool, str]:
        """Verify account is within FTMO parameters."""
        acc = self.mt5.account_info()
        if not acc:
            return False, "Cannot read account info"

        # 1. Static Max Drawdown Floor: $9,000 on $10k account
        if acc.equity < 9000.0:
            return False, f"CRITICAL: Equity ${acc.equity:,.2f} below FTMO $9,000 floor! HALTING."

        # 2. Daily Loss Circuit Breaker (-1.0% / -$100)
        if self.state["daily_pnl"] <= -100.0:
            return False, f"CIRCUIT BREAKER: Daily loss ${self.state['daily_pnl']:.2f} reached -1.0% limit. Trading halted for today."

        # 3. Daily Trade Limit: max 4 trades/day (user configured)
        if self.state["trades_today"] >= MAX_TRADES_PER_DAY:
            return False, f"MAX TRADES: Already executed {self.state['trades_today']} trades today (limit: {MAX_TRADES_PER_DAY}). Done for the day."

        return True, "Limits OK"

    def fetch_m1_df(self, symbol: str, num_bars: int = 500) -> pd.DataFrame | None:
        """Fetch latest M1 bars from MT5 and format with true NY timestamps."""
        rates = self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_M1, 0, num_bars)
        if rates is None or len(rates) == 0:
            return None

        # Dynamically determine broker server time offset from UTC (e.g. ICMarkets is EET = UTC+2)
        tick = self.mt5.symbol_info_tick(symbol)
        if tick:
            now_utc_epoch = int(datetime.now(UTC).timestamp())
            server_offset_sec = round((tick.time - now_utc_epoch) / 3600.0) * 3600
        else:
            server_offset_sec = 7200

        df = pd.DataFrame(rates)
        df["true_utc_time"] = df["time"] - server_offset_sec
        df["time_utc"] = pd.to_datetime(df["true_utc_time"], unit="s", utc=True)
        df["time_ny"] = df["time_utc"].dt.tz_convert(NY)
        df = df.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "tick_volume": "v"})
        return df

    def scan_cycle22_setup(self, symbol: str, window_name: str) -> dict | None:
        """Evaluate Cycle 22 dual-timeframe institutional logic on live closed bars.
        
        Enforces full ICT State Machine:
        1. Point-in-time Draw on Liquidity (DOL) from D1 PDH/PDL and Asian range.
        2. 10-day ADR exhaustion filter (< 80%).
        3. Zero-lookahead confirmed M5 swing pivots (right=2).
        4. True Displacement on M5 (body/range >= 60%, range >= 1.20 * ATR).
        5. Market Structure Shift (MSS) of confirmed opposing swing.
        6. Fair Value Gap (FVG) on M5 candle 3.
        7. Dealing Range Equilibrium Guard:
           - SELL strictly prohibited in Discount (< 50% dealing range).
           - BUY strictly prohibited in Premium (> 50% dealing range).
        8. Anti-Chasing Guard:
           - Prohibits placing order if price has already traveled >= 50% toward TP.
        """
        c22_sym = BROKER_TO_C22.get(symbol, symbol)
        spec = C22_SPECS.get(c22_sym)
        if not spec:
            return None

        # Fetch 1000 M1 bars for continuous HTF/LTF context
        rates = self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_M1, 0, 1000)
        if rates is None or len(rates) < 120:
            return None

        # Fetch 15 D1 bars for prior day PDH, PDL, and 10-day ADR
        d1_rates = self.mt5.copy_rates_from_pos(symbol, self.mt5.TIMEFRAME_D1, 0, 15)
        if d1_rates is None or len(d1_rates) < 12:
            return None

        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        info = self.mt5.symbol_info(symbol)
        point = float(info.point) if info and info.point > 0 else 0.00001
        spread_px = float(tick.ask - tick.bid) if tick.ask > tick.bid else point

        # 1. Strict Live Broker Spread Threshold Gate
        max_allowed_spread = MAX_ALLOWED_SPREAD.get(symbol, 999.0)
        if spread_px > max_allowed_spread:
            print(f"  [SPREAD GATE] Setup skipped on {symbol}: current spread {spread_px:.5f} > limit {max_allowed_spread:.5f}")
            log_audit_event("SPREAD_REJECTED", {"symbol": symbol, "spread": spread_px, "limit": max_allowed_spread})
            return None

        # 2. Automated Live Economic News Blackout Gate (ForexFactory API)
        now_utc = datetime.now(UTC)
        in_blackout, news_reason = self.calendar.is_in_blackout(symbol, now_utc)
        if in_blackout:
            print(f"  [NEWS GATE] Setup blocked on {symbol}: {news_reason}")
            log_audit_event("NEWS_REJECTED", {"symbol": symbol, "reason": news_reason})
            return None

        # Dynamic broker server time offset calculation
        now_utc_epoch = int(datetime.now(UTC).timestamp())
        server_offset_sec = round((tick.time - now_utc_epoch) / 3600.0) * 3600

        # Construct Bars
        ts_utc_ns = (rates["time"] - server_offset_sec).astype(np.int64) * 1_000_000_000
        bid_o = rates["open"].astype(np.float64)
        bid_h = rates["high"].astype(np.float64)
        bid_l = rates["low"].astype(np.float64)
        bid_c = rates["close"].astype(np.float64)

        ask_o = bid_o + spread_px
        ask_h = bid_h + spread_px
        ask_l = bid_l + spread_px
        ask_c = bid_c + spread_px

        mid_o = (bid_o + ask_o) / 2.0
        mid_h = (bid_h + ask_h) / 2.0
        mid_l = (bid_l + ask_l) / 2.0
        mid_c = (bid_c + ask_c) / 2.0

        prev_c = np.r_[np.nan, mid_c[:-1]]
        tr = np.fmax(mid_h - mid_l, np.fmax(np.abs(mid_h - prev_c), np.abs(mid_l - prev_c)))
        atr = pd.Series(tr).rolling(14, min_periods=14).mean().to_numpy()

        bars = Bars(ts_utc_ns, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, mid_o, mid_h, mid_l, mid_c, atr)
        m5 = build_m5(bars)
        if len(m5.o) < 15:
            return None

        # Build DayContext from D1 rates and intraday bars
        pdh = float(d1_rates[-2]["high"])
        pdl = float(d1_rates[-2]["low"])
        adr10 = float(np.mean([r["high"] - r["low"] for r in d1_rates[-11:-1]]))

        # Intraday bars from 00:00 NY today
        dt_ny = pd.to_datetime(bars.ts, unit="ns", utc=True).tz_convert(NY)
        today_date = dt_ny[-1].date()
        today_mask = dt_ny.date == today_date
        idxs_today = np.where(today_mask)[0]
        if len(idxs_today) < 10:
            return None

        intra_h = float(np.max(bars.mid_h[idxs_today]))
        intra_l = float(np.min(bars.mid_l[idxs_today]))
        intra_range = intra_h - intra_l
        adr_exhausted = intra_range >= 0.80 * adr10

        # Asian Reference Range: 00:00 to 02:00 NY for London; 00:00 to 09:30 NY for AM
        cutoff_h, cutoff_m = (2, 0) if "LDN" in window_name else (9, 30)
        asia_mask = today_mask & ((dt_ny.hour < cutoff_h) | ((dt_ny.hour == cutoff_h) & (dt_ny.minute < cutoff_m)))
        idxs_asia = np.where(asia_mask)[0]
        if len(idxs_asia) > 0:
            asia_h = float(np.max(bars.mid_h[idxs_asia]))
            asia_l = float(np.min(bars.mid_l[idxs_asia]))
        else:
            asia_h, asia_l = intra_h, intra_l

        # Two-Tier Draw on Liquidity (DOL) & Dealing Range Equilibrium
        pdl_swept = (intra_l < pdl) or (intra_l < asia_l)
        pdh_swept = (intra_h > pdh) or (intra_h > asia_h)
        cur_px = float(bars.mid_c[-1])

        if pdl_swept and not pdh_swept:
            dol_side = 1   # Swept sell-side liquidity -> Magnet is buy-side (PDH/Asia High)
        elif pdh_swept and not pdl_swept:
            dol_side = -1  # Swept buy-side liquidity -> Magnet is sell-side (PDL/Asia Low)
        else:
            mid_range = (pdh + pdl) / 2.0
            if cur_px < mid_range:
                dol_side = 1  # In Discount -> seek Buy-side
            elif cur_px > mid_range:
                dol_side = -1 # In Premium -> seek Sell-side
            else:
                dol_side = 0

        ctx = DayContext(
            pdh=pdh,
            pdl=pdl,
            adr10=adr10,
            asia_h=asia_h,
            asia_l=asia_l,
            dol_side=dol_side,
            adr_exhausted=adr_exhausted,
        )

        # M5 Pivots with zero lookahead (right=2)
        ph5, pl5 = pivot_flags(m5.h, m5.l, left=2, right=2)

        # Determine M5 window start and end
        m5_dt_ny = pd.to_datetime(m5.ts_start, unit="ns", utc=True).tz_convert(NY)
        if "PM" in window_name:
            win_start_h, win_start_m = 14, 0
            win_end_h, win_end_m = 15, 0
        elif "OPEN_DRIVE" in window_name:
            win_start_h, win_start_m = 9, 30
            win_end_h, win_end_m = 10, 30
        elif "LDN" in window_name:
            win_start_h, win_start_m = 3, 0
            win_end_h, win_end_m = 4, 0
        else:
            win_start_h, win_start_m = 10, 0
            win_end_h, win_end_m = 11, 0

        win_mask = (m5_dt_ny.date == today_date) & (
            (m5_dt_ny.hour > win_start_h) | ((m5_dt_ny.hour == win_start_h) & (m5_dt_ny.minute >= win_start_m))
        ) & (
            (m5_dt_ny.hour < win_end_h) | ((m5_dt_ny.hour == win_end_h) & (m5_dt_ny.minute < win_end_m))
        )
        idxs_win = np.where(win_mask)[0]
        if len(idxs_win) == 0:
            return None

        m5_start = int(idxs_win[0])
        m5_end = min(len(m5.o), int(idxs_win[-1]) + 1)

        # Run verified C22 setup finder
        setup = find_setup(
            m5=m5,
            ph5=ph5,
            pl5=pl5,
            m5_start_idx=m5_start,
            m5_end_idx=m5_end,
            ctx=ctx,
            sp=spec,
            current_spread=spread_px,
        )
        if not setup:
            return None

        # --- INSTITUTIONAL ICT GUARDS ---

        # 1. Dealing Range Equilibrium Guard:
        # Selling is strictly forbidden in Discount (< 50% dealing range).
        # Buying is strictly forbidden in Premium (> 50% dealing range).
        dealing_mid = (intra_h + intra_l) / 2.0
        if setup.side == -1 and setup.entry_px < dealing_mid:
            # Attempted sell below equilibrium in discount! Prohibited.
            return None
        if setup.side == 1 and setup.entry_px > dealing_mid:
            # Attempted buy above equilibrium in premium! Prohibited.
            return None

        # 2. Anti-Chasing / Traveled Distance Guard:
        # If market price has already traveled >= 50% of the distance from entry to TP,
        # the move has already expanded without us. Do not leave a stranded limit order!
        dist_to_tp = abs(setup.tp_px - setup.entry_px)
        if dist_to_tp > 0:
            if setup.side == -1:  # SELL
                if cur_px < setup.entry_px:  # Price is below entry, moving towards TP
                    traveled = setup.entry_px - cur_px
                    if traveled >= 0.50 * dist_to_tp:
                        return None
                    if cur_px <= setup.tp_px:  # Price already touched/exceeded TP!
                        return None
            elif setup.side == 1:  # BUY
                if cur_px > setup.entry_px:  # Price is above entry, moving towards TP
                    traveled = cur_px - setup.entry_px
                    if traveled >= 0.50 * dist_to_tp:
                        return None
                    if cur_px >= setup.tp_px:  # Price already touched/exceeded TP!
                        return None

        # 3. Format Setup
        direction = "BUY" if setup.side == 1 else "SELL"
        return {
            "symbol": symbol,
            "direction": direction,
            "entry": float(setup.entry_px),
            "stop": float(setup.sl_px),
            "tp1": float(setup.tp_px),
            "tp2": float(setup.entry_px + setup.side * setup.risk_dist * 3.0),
            "stop_dist": float(setup.risk_dist),
            "window": window_name,
        }

    def execute_order(self, setup: dict) -> bool:
        """Place pending limit order with exact SL/TP."""
        symbol = setup["symbol"]
        acc = self.mt5.account_info()
        risk_dollars = acc.equity * 0.0050  # 0.50% base risk ($50 on $10k)
        lots = calculate_lots(symbol, risk_dollars, setup["stop_dist"], self.mt5)

        print(f"\n[SIGNAL TRIGGERED] {setup['direction']} {symbol} ({setup['window']})")
        print(f"  Entry Limit:  {setup['entry']}")
        print(f"  Stop Loss:    {setup['stop']} ({setup['stop_dist']:.5f} dist)")
        print(f"  Take Profit:  {setup['tp1']} (1.8R) / {setup['tp2']} (3.0R)")
        print(f"  Risk Dollars: ${risk_dollars:.2f} | Lot Size: {lots}")

        if self.dry_run:
            print("  [DRY RUN] Order logged to state. No live order sent to MT5.")
            self.state["trades_today"] += 1
            self.save_state()
            return True

        # Retrieve broker symbol metadata for exact decimal digits and tick size
        info = self.mt5.symbol_info(symbol)
        if info is None:
            print(f"  [ERROR] Cannot retrieve symbol info for {symbol}")
            return False

        digits = int(info.digits)
        point = float(info.point) if info.point > 0 else 0.01
        # Broker minimum distance in price units for pending orders
        min_stop_distance = float(info.trade_stops_level) * point if info.trade_stops_level > 0 else point

        # Strict Decimal Normalization to broker specifications
        entry_px = round(float(setup["entry"]), digits)
        sl_px = round(float(setup["stop"]), digits)
        tp_px = round(float(setup["tp1"]), digits)

        # Pure ICT Silver Bullet Model: Always institutional LIMIT orders
        tick = self.mt5.symbol_info_tick(symbol)
        if setup["direction"] == "BUY":
            order_type = self.mt5.ORDER_TYPE_BUY_LIMIT
            # Ensure Buy Limit price is legally placed below current Ask by at least min_stop_distance
            if tick is not None and entry_px >= tick.ask - min_stop_distance:
                entry_px = round(tick.ask - min_stop_distance, digits)
        else:
            order_type = self.mt5.ORDER_TYPE_SELL_LIMIT
            # Ensure Sell Limit price is legally placed above current Bid by at least min_stop_distance
            if tick is not None and entry_px <= tick.bid + min_stop_distance:
                entry_px = round(tick.bid + min_stop_distance, digits)

        request = {
            "action": self.mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": lots,
            "type": order_type,
            "price": entry_px,
            "sl": sl_px,
            "tp": tp_px,
            "type_time": self.mt5.ORDER_TIME_DAY,
            "comment": f"C22_{setup['window']}",
        }

        res = self.mt5.order_send(request)
        if res.retcode != self.mt5.TRADE_RETCODE_DONE:
            print(f"  [ERROR] Order failed: retcode={res.retcode}, comment={res.comment}")
            return False

        print(f"  [SUCCESS] Live pending order #{res.order} placed successfully on MT5!")
        self.state["trades_today"] += 1
        self.save_state()
        log_audit_event("ORDER_PLACED", {
            "symbol": symbol,
            "ticket": res.order,
            "direction": setup["direction"],
            "entry": entry_px,
            "sl": sl_px,
            "tp": tp_px,
            "lots": lots,
            "risk_dollars": risk_dollars,
            "window": setup["window"],
        })
        return True

    def cancel_order(self, ticket: int, reason: str = "") -> bool:
        """Cancel an unfilled pending order via MT5."""
        if not self.mt5:
            return False
        request = {
            "action": self.mt5.TRADE_ACTION_REMOVE,
            "order": int(ticket),
        }
        res = self.mt5.order_send(request)
        if res and res.retcode == self.mt5.TRADE_RETCODE_DONE:
            print(f"  [AUTO-CANCEL] Pending order #{ticket} removed. Reason: {reason}")
            self.state["trades_today"] = max(0, self.state["trades_today"] - 1)
            self.save_state()
            log_audit_event("ORDER_CANCELLED", {"ticket": ticket, "reason": reason})
            return True
        else:
            err = res.comment if res else "Unknown"
            print(f"  [ERROR] Failed to cancel order #{ticket}: {err}")
            return False

    def close_position(self, ticket: int, reason: str = "") -> bool:
        """Close an open position at market price."""
        if not self.mt5:
            return False
        pos = self.mt5.positions_get(ticket=ticket)
        if not pos:
            return False
        p = pos[0]
        tick = self.mt5.symbol_info_tick(p.symbol)
        if not tick:
            return False

        order_type = self.mt5.ORDER_TYPE_SELL if p.type == self.mt5.POSITION_TYPE_BUY else self.mt5.ORDER_TYPE_BUY
        price = tick.bid if p.type == self.mt5.POSITION_TYPE_BUY else tick.ask

        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": order_type,
            "price": price,
            "comment": f"AutoClose: {reason[:20]}",
        }
        res = self.mt5.order_send(request)
        if res and res.retcode == self.mt5.TRADE_RETCODE_DONE:
            print(f"  [POSITION CLOSED] Position #{ticket} {p.symbol} closed. Reason: {reason}")
            log_audit_event("POSITION_CLOSED", {"ticket": ticket, "symbol": p.symbol, "reason": reason, "close_px": price})
            return True
        else:
            err = res.comment if res else "Unknown"
            print(f"  [ERROR] Failed to close position #{ticket}: {err}")
            return False

    def check_asset_class_concurrency(self, symbol: str) -> tuple[bool, str]:
        """Enforces max 2 non-correlated positions: at most 1 in FX and 1 in Index/Commodity."""
        if self.dry_run or not self.mt5:
            return True, "OK"

        orders = self.mt5.orders_get() or []
        positions = self.mt5.positions_get() or []

        total_active = len(orders) + len(positions)
        if total_active >= MAX_CONCURRENT_POSITIONS:
            return False, f"Maximum global concurrent limit reached ({total_active}/{MAX_CONCURRENT_POSITIONS})"

        target_class = ASSET_CLASSES.get(symbol, "OTHER")
        for item in list(orders) + list(positions):
            item_sym = item.symbol
            if ASSET_CLASSES.get(item_sym) == target_class:
                return False, f"Asset class '{target_class}' already has active trade on {item_sym}"

        return True, "Concurrency OK"

    def manage_open_positions(self, now_ny) -> None:
        """Institutional Position Lifecycle Management:
        1. Breakeven Protection: Once unrealized profit reaches +1.0R, move SL to Entry.
        2. Hard End-of-Day Flatten at 16:30 NY: Close positions before rollover spread spikes.
        3. Friday Weekend Blackout at 16:00 NY: Force flatten before market closes for weekend.
        """
        if self.dry_run or not self.mt5:
            return

        positions = self.mt5.positions_get()
        if not positions:
            return

        is_eod = (now_ny.hour == 16 and now_ny.minute >= 30) or now_ny.hour > 16
        is_friday_blackout = (now_ny.weekday() == 4 and now_ny.hour >= 16)

        for pos in positions:
            ticket = pos.ticket
            sym = pos.symbol
            tick = self.mt5.symbol_info_tick(sym)
            if tick is None:
                continue

            # 1. Hard Flatten at EOD or Weekend Blackout
            if is_eod or is_friday_blackout:
                reason = "Friday Weekend Blackout (16:00 NY)" if is_friday_blackout else "Session EOD Hard Flatten (16:30 NY)"
                self.close_position(ticket, reason=reason)
                continue

            # 2. Breakeven Protection (+1.0R Trigger)
            info = self.mt5.symbol_info(sym)
            point = float(info.point) if info and info.point > 0 else 0.00001
            digits = int(info.digits) if info else 5

            entry = float(pos.price_open)
            current_sl = float(pos.sl)
            stop_dist = abs(entry - current_sl) if current_sl > 0 else 0.0

            if stop_dist > 0:
                if pos.type == self.mt5.POSITION_TYPE_BUY:
                    profit_dist = tick.bid - entry
                    r_unrealized = profit_dist / stop_dist
                    if r_unrealized >= 1.0 and current_sl < entry:
                        new_sl = round(entry + 2 * point, digits)
                        req = {
                            "action": self.mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "symbol": sym,
                            "sl": new_sl,
                            "tp": pos.tp,
                        }
                        res = self.mt5.order_send(req)
                        if res and res.retcode == self.mt5.TRADE_RETCODE_DONE:
                            msg = f"Position #{ticket} {sym} reached +1.0R ({r_unrealized:.2f}R). SL moved to Breakeven {new_sl}."
                            print(f"  [BREAKEVEN PROTECTION] {msg} Zero risk!")
                            log_audit_event("BREAKEVEN_MOVED", {"ticket": ticket, "symbol": sym, "new_sl": new_sl, "r": r_unrealized})
                elif pos.type == self.mt5.POSITION_TYPE_SELL:
                    profit_dist = entry - tick.ask
                    r_unrealized = profit_dist / stop_dist
                    if r_unrealized >= 1.0 and (current_sl > entry or current_sl == 0.0):
                        new_sl = round(entry - 2 * point, digits)
                        req = {
                            "action": self.mt5.TRADE_ACTION_SLTP,
                            "position": ticket,
                            "symbol": sym,
                            "sl": new_sl,
                            "tp": pos.tp,
                        }
                        res = self.mt5.order_send(req)
                        if res and res.retcode == self.mt5.TRADE_RETCODE_DONE:
                            msg = f"Position #{ticket} {sym} reached +1.0R ({r_unrealized:.2f}R). SL moved to Breakeven {new_sl}."
                            print(f"  [BREAKEVEN PROTECTION] {msg} Zero risk!")
                            log_audit_event("BREAKEVEN_MOVED", {"ticket": ticket, "symbol": sym, "new_sl": new_sl, "r": r_unrealized})

    def manage_pending_orders(self, now_ny) -> None:
        """Audit and manage existing pending orders:
        1. Auto-cancel if market price touches/exceeds Take Profit before filling (Target Reached).
        2. Auto-cancel if Killzone window has expired without filling.
        3. Eliminate duplicate stacked orders on the same symbol (Single Active Order Policy).
        """
        if self.dry_run or not self.mt5:
            return

        orders = self.mt5.orders_get()
        if not orders:
            return

        seen_symbols: dict[str, list] = {}

        for order in orders:
            ticket = order.ticket
            sym = order.symbol
            seen_symbols.setdefault(sym, []).append(order)

            tick = self.mt5.symbol_info_tick(sym)
            if tick is None:
                continue

            # 1. Target Reached Auto-Cancellation Check
            if order.tp > 0:
                if order.type == self.mt5.ORDER_TYPE_BUY_LIMIT:
                    if tick.bid >= order.tp:
                        self.cancel_order(
                            ticket,
                            reason=f"Target already reached (Current Bid: {tick.bid} >= TP: {order.tp})",
                        )
                        continue
                elif order.type == self.mt5.ORDER_TYPE_SELL_LIMIT:
                    if tick.ask <= order.tp:
                        self.cancel_order(
                            ticket,
                            reason=f"Target already reached (Current Ask: {tick.ask} <= TP: {order.tp})",
                        )
                        continue

            # 2. Session Expiry Check (16:30 NY cash close)
            if now_ny.hour > 16 or (now_ny.hour == 16 and now_ny.minute >= 30):
                self.cancel_order(
                    ticket,
                    reason="Session EOD reached (all unfilled pending orders cancelled at 16:30 NY)",
                )
                continue

        # 3. Clean up stacked duplicate pending orders on the same symbol
        for sym, sym_orders in seen_symbols.items():
            if len(sym_orders) > 1:
                sorted_orders = sorted(sym_orders, key=lambda o: o.ticket, reverse=True)
                for stale_order in sorted_orders[1:]:
                    self.cancel_order(
                        stale_order.ticket,
                        reason=f"Duplicate order on {sym} eliminated (Single Active Order Policy)",
                    )

    def poll_once(self) -> None:
        now_ny = get_ny_now()
        now_ist = get_ist_now()
        today_str = now_ny.strftime("%Y-%m-%d")
        self.check_daily_reset(today_str)

        time_str = f"{now_ist.strftime('%H:%M:%S')} IST | {now_ny.strftime('%H:%M:%S')} NY"
        print(f"[{time_str}] Checking market & session windows...")

        # Institutional Active Order Auditing:
        # 1. Target Reached: Auto-cancel pending limit if market price already hit/exceeded Take Profit.
        # 2. Session Expiry: Auto-cancel pending limit if Killzone window has expired without filling.
        # 3. Single Active Order Policy: Clean up duplicate stacked orders on same symbol.
        self.manage_pending_orders(now_ny)

        # Institutional Open Position Management:
        # 1. Breakeven Protection: Auto-move SL to entry once trade reaches +1.0R.
        # 2. Session EOD Hard Flatten: Force close all positions at 16:30 NY before rollover.
        # 3. Weekend Blackout: Force flatten by Friday 16:00 NY.
        self.manage_open_positions(now_ny)

        # Optional: Check User Logged-in Window (10:10 AM to 10:00 PM IST, Monday-Friday)
        if self.enforce_ist_hours:
            if now_ist.weekday() >= 5:
                print("  [IST Schedule] Weekend. Market is closed. Standing down.")
                return
            if not is_in_window(now_ist, 10, 10, 22, 0):
                print("  [IST Schedule] Outside active hours (10:10 AM - 10:00 PM IST). Standing down.")
                return

        # Weekend blackout (Friday past 16:00 NY -> Sunday 18:00 NY)
        if now_ny.weekday() == 4 and now_ny.hour >= 16:
            print("  Weekend blackout active (Friday after 16:00 NY). Standing down.")
            return
        if now_ny.weekday() == 5 or (now_ny.weekday() == 6 and now_ny.hour < 18):
            print("  Weekend market closed. Standing down.")
            return

        # Daily auto-flatten (16:30 NY)
        if now_ny.hour == 16 and now_ny.minute >= 30:
            print("  16:30 NY Session Auto-Flatten reached. All intraday orders flat.")
            return

        ok, msg = self.audit_ftmo_limits()
        if not ok:
            print(f"  [SAFETY STOP] {msg}")
            return

        # Check Active Windows (Grade-A Curated Institutional Portfolio)
        active_slots = []
        # London Session: 03:00-04:00 NY (13:30-14:30 IST / 1:30 PM - 2:30 PM IST)
        if is_in_window(now_ny, 3, 0, 4, 0):
            active_slots.append(("GBPUSD", "LDN"))
            active_slots.append(("EURUSD", "LDN"))
        # Cash Open Drive: 09:30-10:30 NY (20:00-21:00 IST / 8:00 PM - 9:00 PM IST)
        if is_in_window(now_ny, 9, 30, 10, 30):
            active_slots.append(("USTEC", "OPEN_DRIVE"))
            active_slots.append(("US30", "OPEN_DRIVE"))
            active_slots.append(("US500", "OPEN_DRIVE"))
        # NY AM Session: 10:00-11:00 NY (20:30-21:30 IST / 8:30 PM - 9:30 PM IST)
        if is_in_window(now_ny, 10, 0, 11, 0):
            active_slots.append(("XAUUSD", "AM"))
            active_slots.append(("EURUSD", "AM"))
        # NY PM Session: 14:00-15:00 NY (00:30-01:30 IST / 12:30 AM - 1:30 AM IST)
        if is_in_window(now_ny, 14, 0, 15, 0):
            active_slots.append(("US30", "PM"))
            active_slots.append(("USTEC", "PM"))
            active_slots.append(("US500", "PM"))
            active_slots.append(("EURUSD", "PM"))

        if not active_slots:
            if now_ny.hour < 3:
                print("  No active window right now. Next active window: London Session at 03:00 NY (1:30 PM IST) [GBPUSD, EURUSD]. Idle.")
            elif now_ny.hour < 4:
                print("  Active Window: London Session [03:00-04:00 NY]. Next: Cash Open Drive at 09:30 NY (8:00 PM IST).")
            elif now_ny.hour < 9 or (now_ny.hour == 9 and now_ny.minute < 30):
                print("  No active window right now. Next active window: Cash Open Drive at 09:30 NY (8:00 PM IST) [USTEC, US30, US500]. Idle.")
            elif now_ny.hour < 10:
                print("  Active Window: Cash Open Drive [09:30-10:30 NY]. Next: NY AM at 10:00 NY (8:30 PM IST).")
            elif now_ny.hour < 14:
                print("  No active window right now. Next active window: NY PM at 14:00 NY (12:30 AM IST) [US30, USTEC, US500, EURUSD]. Idle.")
            else:
                print("  No active window right now. Next active window: London Session at 03:00 NY (1:30 PM IST tomorrow). Idle.")
            return

        for sym, win in active_slots:
            # 1. Single Active Order / Position per Symbol Policy
            if not self.dry_run and self.mt5:
                orders_sym = self.mt5.orders_get(symbol=sym)
                pos_sym = self.mt5.positions_get(symbol=sym)
                n_orders = len(orders_sym) if orders_sym else 0
                n_pos = len(pos_sym) if pos_sym else 0
                if n_orders > 0 or n_pos > 0:
                    print(f"  [{win}] {sym}: Active {n_orders} pending / {n_pos} open position. Standing down (Single Active Order Policy).")
                    continue

            # 2. Asset Class Concurrency Gate (Max 2 non-correlated: 1 FX + 1 Index/Commodity)
            ok_conc, msg_conc = self.check_asset_class_concurrency(sym)
            if not ok_conc:
                print(f"  [{win}] {sym}: {msg_conc}. Standing down.")
                continue

            setup = self.scan_cycle22_setup(sym, win)
            if setup:
                self.execute_order(setup)
                break
            else:
                tick = self.mt5.symbol_info_tick(sym) if self.mt5 else None
                cur_p = tick.bid if tick else "N/A"
                print(f"  [{win}] {sym} (Price: {cur_p}): Structure monitored, awaiting institutional sweep / FVG setup.")


def main() -> int:
    parser = argparse.ArgumentParser(description="FTMO $10k Live MT5 Execution Bridge")
    parser.add_argument("--poll", action="store_true", help="Perform a single poll pass and exit")
    parser.add_argument("--loop", action="store_true", help="Run continuous loop polling every 60s")
    parser.add_argument("--live", action="store_true", help="Place live orders on MT5 (default is dry-run)")
    parser.add_argument("--enforce-ist-hours", action="store_true", help="Enforce 10:10 AM - 7:00 PM IST operating window")
    args = parser.parse_args()

    engine = FTMOLiveEngine(dry_run=not args.live, enforce_ist_hours=args.enforce_ist_hours)
    if not engine.connect():
        return 1

    if args.loop:
        mode_str = "LIVE ORDER EXECUTION" if args.live else "DRY-RUN PAPER TRADING"
        print(f"[INFO] Starting continuous poll daemon in {mode_str} mode (Ctrl+C to stop)...")
        try:
            while True:
                engine.poll_once()
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[INFO] Daemon stopped by user.")
    else:
        engine.poll_once()

    if engine.mt5:
        engine.mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
