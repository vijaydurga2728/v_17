"""Ingest multi-year XAUUSD and DE40 M1 bars from MT5 into data/bars_m1_paired."""
import os
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import dotenv
import MetaTrader5 as mt5
import numpy as np
import pandas as pd

dotenv.load_dotenv()
REPO = Path(__file__).resolve().parents[1]

login = int(os.environ.get("MT5_LOGIN", 0))
pwd = os.environ.get("MT5_PASSWORD", "")
server = os.environ.get("MT5_SERVER", "")

if not mt5.initialize(login=login, password=pwd, server=server):
    print("MT5 initialization failed!", flush=True)
    sys.exit(1)

print("MT5 initialized successfully.", flush=True)

start_dt = datetime(2021, 1, 1, tzinfo=timezone.utc)
end_dt = datetime(2026, 11, 21, tzinfo=timezone.utc)

# Server is UTC+2 outside DST, UTC+3 in summer DST
# We determine offset using broker time vs UTC
term_info = mt5.terminal_info()

for sym in ["XAUUSD", "DE40"]:
    print(f"Fetching M1 bars for {sym}...", flush=True)
    mt5.symbol_select(sym, True)
    sym_info = mt5.symbol_info(sym)
    point = sym_info.point if sym_info else 0.01

    rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M1, start_dt, end_dt)
    if rates is None or len(rates) == 0:
        print(f"No rates returned for {sym}!", flush=True)
        continue

    print(f"  Received {len(rates):,} raw bars for {sym}. Converting...", flush=True)
    df = pd.DataFrame(rates)
    
    # Time in rates is server time (UTC+2 or UTC+3 depending on DST)
    # Convert server time to UTC
    # Broker time is EET/EEST ('Europe/Helsinki' or 'Europe/Athens' is exact match for MT5 server time)
    server_tz = ZoneInfo("Europe/Helsinki")
    # Convert epoch seconds directly to UTC via server timezone
    server_dt = pd.to_datetime(df["time"], unit="s").dt.tz_localize(server_tz)
    utc_dt = server_dt.dt.tz_convert(timezone.utc)
    
    ts_utc = utc_dt.astype("int64").to_numpy()
    
    bid_o = df["open"].to_numpy(np.float64)
    bid_h = df["high"].to_numpy(np.float64)
    bid_l = df["low"].to_numpy(np.float64)
    bid_c = df["close"].to_numpy(np.float64)
    spread = df["spread"].to_numpy(np.float64) * point
    
    ask_o = bid_o + spread
    ask_h = bid_h + spread
    ask_l = bid_l + spread
    ask_c = bid_c + spread
    
    vol = df["tick_volume"].to_numpy(np.int64)
    
    out_df = pd.DataFrame({
        "ts_utc": ts_utc,
        "symbol": sym,
        "bid_o": bid_o,
        "bid_h": bid_h,
        "bid_l": bid_l,
        "bid_c": bid_c,
        "ask_o": ask_o,
        "ask_h": ask_h,
        "ask_l": ask_l,
        "ask_c": ask_c,
        "bid_volume": vol,
        "ask_volume": vol,
        "spread_mid": spread,
    })
    
    out_dir = REPO / "data" / "bars_m1_paired" / sym
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Save partitioned by year
    years = utc_dt.dt.year.to_numpy()
    for yr in np.unique(years):
        yr_dir = out_dir / f"year={yr}"
        yr_dir.mkdir(parents=True, exist_ok=True)
        mask = years == yr
        sub_df = out_df[mask].reset_index(drop=True)
        sub_df.to_parquet(yr_dir / "data.parquet", index=False)
        print(f"  Saved {sym} year={yr}: {len(sub_df):,} bars", flush=True)

mt5.shutdown()
print("All data ingestion complete!", flush=True)
