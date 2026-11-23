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
tick = mt5.symbol_info_tick('GBPUSD')
now_utc_epoch = int(datetime.now(timezone.utc).timestamp())
server_offset_sec = round((tick.time - now_utc_epoch) / 3600.0) * 3600
print(f"Detected Broker Server Offset from UTC: {server_offset_sec / 3600:.1f} hours ({server_offset_sec}s)")

# Fetch 1000 M1 bars
rates = mt5.copy_rates_from_pos('GBPUSD', mt5.TIMEFRAME_M1, 0, 1000)
mt5.shutdown()

df = pd.DataFrame(rates)
# Correct the epoch by subtracting broker server offset
df['true_utc_time'] = df['time'] - server_offset_sec
df['time_utc'] = pd.to_datetime(df['true_utc_time'], unit='s', utc=True)
df['time_ist'] = df['time_utc'].dt.tz_convert(IST)
df['time_ny'] = df['time_utc'].dt.tz_convert(NY)

today_ny = df['time_ny'].iloc[-1].date()
today_df = df[df['time_ny'].dt.date == today_ny].copy()

print(f"\n================================================================================")
print(f"GBPUSD TRUE PRICE ACTION AUDIT: Date {today_ny} (Current Time: {datetime.now(IST).strftime('%H:%M:%S')} IST)")
print(f"================================================================================")

# Asian Range: 19:00 NY (prev day) to 00:00 or 02:00 NY (London open)
# In NY time: 20:00 to 02:00 NY
asia_df = df[(df['time_ny'] >= pd.Timestamp(today_ny).tz_localize(NY)) & (df['time_ny'] < pd.Timestamp(today_ny).tz_localize(NY) + pd.Timedelta(hours=2))]
# Or check the 6 hours preceding 02:00 NY
ldn_open_ny = pd.Timestamp(today_ny).tz_localize(NY) + pd.Timedelta(hours=2)
pre_ldn = df[(df['time_ny'] >= ldn_open_ny - pd.Timedelta(hours=6)) & (df['time_ny'] < ldn_open_ny)]

asia_high = pre_ldn['high'].max()
asia_low = pre_ldn['low'].min()
print(f"Asian / Pre-London Range (20:00 - 02:00 NY / 06:30 - 12:30 IST):")
print(f"  Asia High: {asia_high:.5f}")
print(f"  Asia Low:  {asia_low:.5f}")
print(f"  Asia Range: {((asia_high - asia_low) * 10000):.1f} pips")

# London Killzone: 02:00 NY to 05:00 NY (12:30 IST to 15:30 IST)
ldn_kz = today_df[(today_df['time_ny'].dt.hour >= 2) & (today_df['time_ny'].dt.hour < 5)].copy()
print(f"\nLondon Killzone (02:00 - 05:00 NY / 12:30 - 15:30 IST):")
print(f"  Total M1 candles: {len(ldn_kz)}")
if len(ldn_kz) > 0:
    ldn_high = ldn_kz['high'].max()
    ldn_low = ldn_kz['low'].min()
    h_time = ldn_kz.loc[ldn_kz['high'].idxmax(), 'time_ist'].strftime('%H:%M:%S')
    l_time = ldn_kz.loc[ldn_kz['low'].idxmin(), 'time_ist'].strftime('%H:%M:%S')
    print(f"  London Killzone High: {ldn_high:.5f} at {h_time} IST")
    print(f"  London Killzone Low:  {ldn_low:.5f} at {l_time} IST")
    print(f"  London Killzone Range: {((ldn_high - ldn_low) * 10000):.1f} pips")

    swept_high = ldn_high > asia_high
    swept_low = ldn_low < asia_low
    print(f"\nDid London sweep Asia High ({asia_high:.5f})? {'YES ->' if swept_high else 'NO (High not swept)'}")
    print(f"Did London sweep Asia Low  ({asia_low:.5f})? {'YES ->' if swept_low else 'NO (Low not swept)'}")
    
    if not swept_high and not swept_low:
        print("\n>>> CONCLUSION: London was completely INSIDE the Asian range! Contained / Consolidation session. <<<")
        print(">>> An institutional ICT strategy strictly refuses to trade inside consolidation to prevent whipsaws. <<<")
