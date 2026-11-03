from decimal import Decimal
import pandas as pd
from v17.common.types import TF, Symbol
from v17.config import get_settings
from v17.data.providers import ParquetBarProvider

s = get_settings()
p = ParquetBarProvider(s.parquet_root)
trades = pd.read_parquet('runs/fc5e94ebb80034d3/trades.parquet')

print("=== MFE (Maximum Favorable Excursion) of NAS100 15 Trades ===")
for i, r in trades.iterrows():
    sym = Symbol(r['symbol'])
    entry = float(r['entry'])
    sl = float(r['sl'])
    sl_dist = abs(entry - sl)
    open_ts = r['opened_at']
    close_ts = r['closed_at']
    bars = [b.model_dump() for b in p.bars(sym, TF.M1, open_ts, close_ts)]
    df_b = pd.DataFrame(bars)
    if df_b.empty:
        continue
    if r['side'] == 'buy':
        max_fav = float(df_b['high'].astype(float).max()) - entry
        mfe_r = max_fav / sl_dist
    else:
        max_fav = entry - float(df_b['low'].astype(float).min())
        mfe_r = max_fav / sl_dist
    print(f"Trade #{i+1:2d} | {r['side']:4s} | SL: {sl_dist:5.2f} pts | Actual: {r['reason']} | MFE: {max_fav:6.2f} pts ({mfe_r:4.1f}R)")
