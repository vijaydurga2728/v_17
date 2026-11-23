import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
login = int(os.environ['MT5_LOGIN'])
pwd = os.environ['MT5_PASSWORD']
srv = os.environ['MT5_SERVER']

NY = ZoneInfo('America/New_York')
IST = ZoneInfo('Asia/Kolkata')

mt5.initialize(login=login, password=pwd, server=srv)
rates = mt5.copy_rates_from_pos('GBPUSD', mt5.TIMEFRAME_M1, 0, 1000)
mt5.shutdown()

df = pd.DataFrame(rates)
df['true_utc_time'] = df['time'] - 7200
df['time_utc'] = pd.to_datetime(df['true_utc_time'], unit='s', utc=True)
df['time_ist'] = df['time_utc'].dt.tz_convert(IST)
df['time_ny'] = df['time_utc'].dt.tz_convert(NY)

# Look at 14:25 to 15:15 IST
window = df[(df['time_ist'].dt.hour == 14) & (df['time_ist'].dt.minute >= 25) | (df['time_ist'].dt.hour == 15) & (df['time_ist'].dt.minute <= 15)].copy()

print("M1 Candles around the sweep at 14:34 IST:")
print(window[['time_ist', 'open', 'high', 'low', 'close', 'tick_volume']].to_string(index=False))

# Build M5 candles
m5 = df.set_index('time_ist').resample('5min').agg({
    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'tick_volume': 'sum'
}).dropna().reset_index()

m5_window = m5[(m5['time_ist'].dt.hour == 14) | (m5['time_ist'].dt.hour == 15)].copy()
print("\nM5 Candles:")
print(m5_window[['time_ist', 'open', 'high', 'low', 'close']].to_string(index=False))
