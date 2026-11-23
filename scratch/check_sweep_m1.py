import os
from datetime import datetime, UTC
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
rates = mt5.copy_rates_from_pos('GBPUSD', mt5.TIMEFRAME_M1, 0, 100)
mt5.shutdown()

df = pd.DataFrame(rates)
df['time_utc'] = pd.to_datetime(df['time'], unit='s', utc=True)
df['time_ist'] = df['time_utc'].dt.tz_convert(IST)
df['time_ny'] = df['time_utc'].dt.tz_convert(NY)

# Filter for 15:00 to 15:35 IST
recent = df[df['time_ist'].dt.hour == 15].copy()
print(recent[['time_ist', 'open', 'high', 'low', 'close', 'tick_volume']].tail(25).to_string(index=False))
