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

if not mt5.initialize(login=login, password=pwd, server=srv):
    print('Failed to init MT5')
    exit(1)

# Fetch 1000 M1 bars to cover full day (Asia session + London session)
rates = mt5.copy_rates_from_pos('GBPUSD', mt5.TIMEFRAME_M1, 0, 1000)
mt5.shutdown()

if rates is None or len(rates) == 0:
    print('No rates fetched')
    exit(1)

df = pd.DataFrame(rates)
df['time_utc'] = pd.to_datetime(df['time'], unit='s', utc=True)
df['time_ist'] = df['time_utc'].dt.tz_convert(IST)
df['time_ny'] = df['time_utc'].dt.tz_convert(NY)

today_ist = df['time_ist'].iloc[-1].date()
today_df = df[df['time_ist'].dt.date == today_ist].copy()

print(f"================================================================================")
print(f"GBPUSD FORENSIC DIAGNOSIS FOR TODAY: {today_ist} (Current Time: {datetime.now(IST).strftime('%H:%M:%S')} IST)")
print(f"================================================================================")

# 1. Asian Session (05:30 IST to 11:30 IST / 19:00 to 01:00 NY)
asia_df = today_df[(today_df['time_ist'].dt.hour >= 5) & (today_df['time_ist'].dt.hour < 12)].copy()
asia_high = asia_df['high'].max() if len(asia_df) > 0 else None
asia_low = asia_df['low'].min() if len(asia_df) > 0 else None

print(f"1. ASIAN SESSION REFERENCE RANGE (05:30 - 11:30 IST):")
if asia_high and asia_low:
    print(f"   Asia High (Liquidity Pool Buy-Side):  {asia_high:.5f}")
    print(f"   Asia Low  (Liquidity Pool Sell-Side): {asia_low:.5f}")
    print(f"   Asia Range: {((asia_high - asia_low) * 10000):.1f} pips")
else:
    print("   Insufficient Asia bars.")

# 2. London Killzone (12:30 IST to 15:30 IST / 02:00 to 05:00 NY)
ldn_df = today_df[
    ((today_df['time_ist'].dt.hour == 12) & (today_df['time_ist'].dt.minute >= 30)) |
    ((today_df['time_ist'].dt.hour > 12) & (today_df['time_ist'].dt.hour < 15)) |
    ((today_df['time_ist'].dt.hour == 15) & (today_df['time_ist'].dt.minute <= 30))
].copy()

print(f"\n2. LONDON KILLZONE PRICE ACTION (12:30 - 15:30 IST):")
print(f"   Bars Recorded: {len(ldn_df)}")
if len(ldn_df) > 0:
    ldn_high = ldn_df['high'].max()
    ldn_low = ldn_df['low'].min()
    h_time = ldn_df.loc[ldn_df['high'].idxmax(), 'time_ist'].strftime('%H:%M')
    l_time = ldn_df.loc[ldn_df['low'].idxmin(), 'time_ist'].strftime('%H:%M')
    print(f"   London High: {ldn_high:.5f} (at {h_time} IST)")
    print(f"   London Low:  {ldn_low:.5f} (at {l_time} IST)")
    print(f"   London Range: {((ldn_high - ldn_low) * 10000):.1f} pips")

    # Check Liquidity Sweeps
    if asia_high and asia_low:
        swept_asia_high = ldn_high >= asia_high
        swept_asia_low = ldn_low <= asia_low
        print(f"\n3. TWO-TIER DRAW ON LIQUIDITY (DOL) VERIFICATION:")
        print(f"   Swept Asia High ({asia_high:.5f})? {'YES [BEARISH SETUP ELIGIBLE]' if swept_asia_high else 'NO'}")
        print(f"   Swept Asia Low  ({asia_low:.5f})? {'YES [BULLISH SETUP ELIGIBLE]' if swept_asia_low else 'NO'}")

# 4. Check Cycle 22 Setup Evaluator across the entire London Killzone
from v17.setups import c22_silver_bullet as sb
sb.WINDOWS["LDN_KZ"] = ((2, 0), (5, 0))
sb.SESSION_ENDS["LDN_KZ"] = (8, 0)
sb.SPECS["GBPUSD"] = sb.Spec(min_stop=0.0010, max_stop=0.0035, slip=0.00005, commission_rt=0.00006)

b_df = sb.prepare(df.rename(columns={'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'tick_volume': 'volume'}))
slots = b_df[(b_df['time_ny'].dt.date == today_df['time_ny'].iloc[-1].date())]
print(f"\n4. SCANNING M5 DISPLACEMENT & M1 FVG DETECTOR:")

# Resample to M5
m5_df = df.set_index('time_ny').resample('5min').agg({
    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'tick_volume': 'sum'
}).dropna().reset_index()

today_m5 = m5_df[m5_df['time_ny'].dt.hour.isin([2, 3, 4])].copy()
print(f"   Total M5 candles during London Killzone: {len(today_m5)}")
print(today_m5[['time_ny', 'open', 'high', 'low', 'close']].tail(10).to_string(index=False))
