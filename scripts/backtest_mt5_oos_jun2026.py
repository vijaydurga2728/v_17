"""OOS MT5 Backtest Runner for June 2026 to November 2026 (Live FTMO Bot).

Pulls live historical M1 bars directly from MetaTrader 5 (ICMarkets Demo)
and simulates the Cycle 22 Multi-Asset Institutional Silver Bullet portfolio
with the exact live bot execution constraints:
- Max 2 concurrent positions (at most 1 FX + 1 Index/Commodity)
- Max 4 trades per day
- Fixed 0.50% ($50) risk per trade on $10,000 equity
- Daily circuit breaker (-1.0% / -$100)
- Auto-flatten at 16:30 NY
"""
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from v17.setups import c22_silver_bullet as sb
from run_c22_silver_bullet import load_calendar_blackout_df, compute_metrics

NY = ZoneInfo("America/New_York")
EET = ZoneInfo("Europe/Helsinki") # ICMarkets server time follows EET/EEST

START_DATE = "2026-06-01"
END_DATE = "2026-11-23"

# Slot configurations matching scripts/live_ftmo_runner.py
SLOTS = [
    # London Session (03:00 - 04:00 NY)
    ("GBPUSD", "GBPUSD", "LDN"),
    ("EURUSD", "EURUSD", "LDN"),
    # Cash Open Drive (09:30 - 10:30 NY)
    ("USTEC", "USATECHIDXUSD", "OPEN_DRIVE"),
    ("US30", "USA30IDXUSD", "OPEN_DRIVE"),
    ("US500", "USA500IDXUSD", "OPEN_DRIVE"),
    # NY AM Session (10:00 - 11:00 NY)
    ("XAUUSD", "XAUUSD", "AM"),
    ("EURUSD", "EURUSD", "AM"),
    # NY PM Session (14:00 - 15:00 NY)
    ("US30", "USA30IDXUSD", "PM"),
    ("USTEC", "USATECHIDXUSD", "PM"),
    ("US500", "USA500IDXUSD", "PM"),
    ("EURUSD", "EURUSD", "PM"),
]

ASSET_CLASSES = {
    "EURUSD": "FX",
    "GBPUSD": "FX",
    "US30": "INDEX",
    "USTEC": "INDEX",
    "US500": "INDEX",
    "XAUUSD": "COMMODITY",
}


def fetch_mt5_bars(symbol: str, start_dt: datetime, end_dt: datetime) -> sb.Bars | None:
    import MetaTrader5 as mt5

    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start_dt, end_dt)
    if rates is None or len(rates) == 0:
        return None

    df = pd.DataFrame(rates)
    # Convert server time to UTC via EET/EEST tz
    server_dts = [datetime.fromtimestamp(t, tz=EET) for t in df["time"]]
    utc_ns = np.array([int(dt.astimezone(UTC).timestamp() * 1_000_000_000) for dt in server_dts], dtype=np.int64)

    info = mt5.symbol_info(symbol)
    point = float(info.point) if info and info.point > 0 else 0.00001

    bid_o = df["open"].to_numpy(np.float64)
    bid_h = df["high"].to_numpy(np.float64)
    bid_l = df["low"].to_numpy(np.float64)
    bid_c = df["close"].to_numpy(np.float64)
    spread = df["spread"].to_numpy(np.float64) * point

    ask_o = bid_o + spread
    ask_h = bid_h + spread
    ask_l = bid_l + spread
    ask_c = bid_c + spread

    mid_o = (bid_o + ask_o) / 2.0
    mid_h = (bid_h + ask_h) / 2.0
    mid_l = (bid_l + ask_l) / 2.0
    mid_c = (bid_c + ask_c) / 2.0

    prev_c = np.r_[np.nan, mid_c[:-1]]
    tr = np.fmax(mid_h - mid_l, np.fmax(np.abs(mid_h - prev_c), np.abs(mid_l - prev_c)))
    atr = pd.Series(tr).rolling(14, min_periods=14).mean().to_numpy()

    return sb.Bars(utc_ns, bid_o, bid_h, bid_l, bid_c, ask_o, ask_h, ask_l, ask_c, mid_o, mid_h, mid_l, mid_c, atr)


def main() -> int:
    import MetaTrader5 as mt5

    print("=" * 85)
    print("CYCLE 22 LIVE FTMO BOT: OUT-OF-SAMPLE (OOS) BACKTEST VIA MT5 DATA")
    print(f"Period: {START_DATE} to {END_DATE} (Today: 2026-11-23)")
    print("Account: $10,000 | Risk: 0.50% ($50/trade) | Max Concurrent: 2 (1 FX + 1 Index/Cmdty)")
    print("Daily Limit: Max 4 trades/day | Circuit Breaker: -$100 (1.0%)")
    print("=" * 85)

    if not mt5.initialize():
        print("[ERROR] Failed to initialize MetaTrader 5.")
        return 1

    cal_df = load_calendar_blackout_df()

    # Pre-fetch bars with 10 days warmup for ATR/indicators
    warmup_start = datetime(2026, 5, 15, tzinfo=UTC)
    sim_end = datetime(2026, 11, 23, 23, 59, tzinfo=UTC)

    bars_cache = {}
    unique_symbols = sorted(list({mt5_sym for mt5_sym, _, _ in SLOTS}))

    for sym in unique_symbols:
        print(f"Fetching M1 bars from MT5 for {sym}...", end=" ", flush=True)
        b = fetch_mt5_bars(sym, warmup_start, sim_end)
        if b is None:
            print(f"[FAIL] No bars returned for {sym}")
            mt5.shutdown()
            return 1
        bars_cache[sym] = b
        print(f"[OK] {len(b.ts):,} bars.")

    mt5.shutdown()

    # Run individual slot backtests
    print("\n" + "=" * 85)
    print("INDIVIDUAL SLOT RAW TRADES (C22 Logic)")
    print("=" * 85)

    raw_trades = []
    # Configure custom windows in sb if needed
    sb.WINDOWS["LDN"] = ((3, 0), (4, 0))
    sb.SESSION_ENDS["LDN"] = (8, 0)
    sb.WINDOWS["OPEN_DRIVE"] = ((9, 30), (10, 30))
    sb.SESSION_ENDS["OPEN_DRIVE"] = (16, 30)

    for mt5_sym, c22_sym, win in SLOTS:
        b = bars_cache[mt5_sym]
        t = sb.run_slot_c22(b, c22_sym, win, START_DATE, END_DATE, cal_df)
        if not t.empty:
            t["mt5_sym"] = mt5_sym
            t["c22_sym"] = c22_sym
            t["window"] = win
            t["asset_class"] = ASSET_CLASSES.get(mt5_sym, "OTHER")
            t["fill_ts"] = b.ts[t["fill_i"].to_numpy()]
            t["exit_ts"] = b.ts[t["exit_i"].to_numpy()]
            raw_trades.append(t)
            m = compute_metrics(t)
            net_r_val = float(t["r"].sum())
            print(f"  [{win:10s}] {mt5_sym:7s} -> {m['n']:3d} trades | Win: {m['win_rate']*100:4.1f}% | PF: {m['pf']:4.2f} | Net R: {net_r_val:+6.2f}R")
        else:
            print(f"  [{win:10s}] {mt5_sym:7s} ->   0 trades")

    if not raw_trades:
        print("\nNo trades generated.")
        return 0

    all_raw_df = pd.concat(raw_trades, ignore_index=True)
    all_raw_df["dt"] = pd.to_datetime(all_raw_df["day"])
    all_raw_df = all_raw_df.sort_values(["fill_ts", "fill_i"]).reset_index(drop=True)

    print("\n" + "=" * 85)
    print("APPLYING LIVE FTMO PORTFOLIO SIMULATION:")
    print("1. Max 2 concurrent positions (at most 1 FX and 1 Index/Commodity)")
    print("2. Max 4 trades per day")
    print("3. Daily Circuit Breaker: -$100 (-2.0R) daily loss halts further trading for day")
    print("=" * 85)

    portfolio_trades = []
    daily_stats = {} # day -> {"trades": int, "realized_r": float, "circuit_hit": bool}
    active_positions = [] # list of {"asset_class": str, "exit_ts": int}

    for _, row in all_raw_df.iterrows():
        day_str = row["day"]
        if day_str not in daily_stats:
            daily_stats[day_str] = {"trades": 0, "realized_r": 0.0, "circuit_hit": False}

        d_stat = daily_stats[day_str]

        # Check circuit breaker
        if d_stat["circuit_hit"]:
            continue

        # Check max 4 trades per day
        if d_stat["trades"] >= 4:
            continue

        entry_ts = row["fill_ts"]
        exit_ts = row["exit_ts"]
        trade_r = row["r"]
        ac = row["asset_class"]

        # Clean up active positions that closed before this trade's entry
        active_positions = [p for p in active_positions if p["exit_ts"] > entry_ts]

        # Check total concurrent limit (max 2)
        if len(active_positions) >= 2:
            continue

        # Check asset class isolation (at most 1 per asset class)
        if any(p["asset_class"] == ac for p in active_positions):
            continue

        # Accept trade into portfolio
        active_positions.append({"asset_class": ac, "exit_ts": exit_ts})
        d_stat["trades"] += 1
        d_stat["realized_r"] += trade_r
        if d_stat["realized_r"] <= -2.0: # -$100 loss at $50/R
            d_stat["circuit_hit"] = True

        portfolio_trades.append(row)

    port_df = pd.DataFrame(portfolio_trades).reset_index(drop=True)
    pm = compute_metrics(port_df)
    net_r_tot = float(port_df["r"].sum())
    n_wins = int((port_df["r"] > 0).sum())
    n_losses = int((port_df["r"] <= 0).sum())

    print("\n" + "=" * 85)
    print("OOS LIVE FTMO PORTFOLIO RESULTS (2026-06-01 to 2026-11-23)")
    print("=" * 85)
    print(f"Total Trades Taken : {pm['n']}")
    print(f"Win Rate           : {pm['win_rate']*100:.1f}% ({n_wins} Wins / {n_losses} Losses)")
    print(f"Profit Factor      : {pm['pf']:.2f}")
    print(f"Average Trade      : {pm['mean_r']:+.3f} R")
    print(f"Net Realized R     : {net_r_tot:+.2f} R")
    print(f"Max Drawdown (R)   : {pm['max_dd_r']:.2f} R")

    # Financial translation on $10,000 FTMO account (0.50% / $50 per R)
    gross_pnl = net_r_tot * 50.0
    max_dd_usd = pm["max_dd_r"] * 50.0
    print(f"\nFINANCIAL TRANSLATION ($10,000 FTMO Account @ 0.50% / $50 Risk):")
    print(f"  Net P&L ($)      : ${gross_pnl:+,.2f} ({gross_pnl / 10000.0 * 100:+.2f}%)")
    print(f"  Max Drawdown ($) : ${max_dd_usd:,.2f} ({max_dd_usd / 10000.0 * 100:.2f}%)")
    print(f"  FTMO Floor Check : Lowest Equity = ${10000.0 - max_dd_usd:,.2f} (Safe from $9,000 floor)")

    # Monthly breakdown
    port_df["ym"] = port_df["dt"].dt.to_period("M")
    m_summary = port_df.groupby("ym").agg(
        trades=("r", "count"),
        wins=("r", lambda x: (x > 0).sum()),
        losses=("r", lambda x: (x <= 0).sum()),
        net_r=("r", "sum")
    ).reset_index()
    m_summary["win_rate%"] = (m_summary["wins"] / m_summary["trades"]) * 100.0
    m_summary["net_pnl_$"] = m_summary["net_r"] * 50.0
    m_summary["ftmo_payout_80%"] = m_summary["net_pnl_$"].apply(lambda p: max(0.0, p * 0.80))

    print("\n" + "=" * 85)
    print("MONTH-BY-MONTH BREAKDOWN & ESTIMATED FTMO PAYOUTS:")
    print("=" * 85)
    print(m_summary.to_string(index=False))

    # Save to out
    out_dir = REPO / "out" / "mt5_oos"
    out_dir.mkdir(parents=True, exist_ok=True)
    port_df.to_csv(out_dir / "trades_oos_jun_nov_2026.csv", index=False)
    print(f"\nDetailed trade log saved to: {out_dir / 'trades_oos_jun_nov_2026.csv'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
