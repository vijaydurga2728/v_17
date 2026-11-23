import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()
mt5.initialize(login=int(os.environ['MT5_LOGIN']), password=os.environ['MT5_PASSWORD'], server=os.environ['MT5_SERVER'])
mt5.symbol_select('XAUUSD', True)
rates = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M1, 0, 30000)
mt5.shutdown()

df = pd.DataFrame(rates)
NY = ZoneInfo('America/New_York')
df['time_utc'] = pd.to_datetime(df['time'] - 7200, unit='s', utc=True)
df['time_ny'] = df['time_utc'].dt.tz_convert(NY)

# Calibrate Gold spec:
# Gold price is ~$3734.
# Min stop: $2.50 ($25 pips), Max stop: $10.00 ($100 pips). Spread: $0.16. Slip: $0.10.
min_stop = 2.50
max_stop = 10.00
cost = 0.26  # spread + slippage

# Group by day
df['day'] = df['time_ny'].dt.date
grouped = df.groupby('day')

trades = []
for day, day_df in grouped:
    # 1. NY AM session: 10:00 to 11:00 NY
    am_df = day_df[(day_df['time_ny'].dt.hour == 10)].copy()
    if len(am_df) < 30:
        continue

    # Previous session range (07:00 to 10:00 NY)
    pre_am = day_df[(day_df['time_ny'].dt.hour >= 7) & (day_df['time_ny'].dt.hour < 10)]
    if len(pre_am) < 30:
        continue
    sess_high = pre_am['high'].max()
    sess_low = pre_am['low'].min()

    # Look for sweep in first 30 mins, then FVG
    for i in range(10, len(am_df) - 5):
        bar = am_df.iloc[i]
        prev = am_df.iloc[i - 1]
        fvg = am_df.iloc[i - 2]

        # Bullish: swept low, disp up, FVG
        if am_df.iloc[:i]['low'].min() <= sess_low and bar['close'] > bar['open'] and bar['low'] > fvg['high']:
            entry = fvg['high']
            stop = am_df.iloc[:i]['low'].min() - 0.50
            dist = entry - stop
            if min_stop <= dist <= max_stop:
                tp1 = entry + dist * 1.8
                # Check forward resolution
                future = day_df[day_df.index > bar.name]
                if len(future) == 0:
                    continue
                # Simulation resolution
                hit_sl = future['low'].min() <= stop
                hit_tp = future['high'].max() >= tp1
                sl_idx = future[future['low'] <= stop].index.min() if hit_sl else 999999
                tp_idx = future[future['high'] >= tp1].index.min() if hit_tp else 999999
                r = 1.8 if tp_idx < sl_idx else -1.0
                trades.append({'day': day, 'dir': 'BUY', 'entry': entry, 'stop': stop, 'r': r})
                break

        # Bearish: swept high, disp down, FVG
        elif am_df.iloc[:i]['high'].max() >= sess_high and bar['close'] < bar['open'] and bar['high'] < fvg['low']:
            entry = fvg['low']
            stop = am_df.iloc[:i]['high'].max() + 0.50
            dist = stop - entry
            if min_stop <= dist <= max_stop:
                tp1 = entry - dist * 1.8
                future = day_df[day_df.index > bar.name]
                if len(future) == 0:
                    continue
                hit_sl = future['high'].max() >= stop
                hit_tp = future['low'].min() <= tp1
                sl_idx = future[future['high'] >= stop].index.min() if hit_sl else 999999
                tp_idx = future[future['low'] <= tp1].index.min() if hit_tp else 999999
                r = 1.8 if tp_idx < sl_idx else -1.0
                trades.append({'day': day, 'dir': 'SELL', 'entry': entry, 'stop': stop, 'r': r})
                break

tdf = pd.DataFrame(trades)
print(f"XAUUSD (Gold) NY AM Evaluation:")
print(f"Total trades: {len(tdf)}")
if len(tdf) > 0:
    wins = (tdf['r'] > 0).sum()
    losses = (tdf['r'] < 0).sum()
    wr = wins / len(tdf) * 100
    total_r = tdf['r'].sum()
    pf = (wins * 1.8) / losses if losses > 0 else 999
    print(f"Wins: {wins} | Losses: {losses} | Win Rate: {wr:.1f}%")
    print(f"Total Return: {total_r:+.2f} R | Profit Factor: {pf:.2f}")
