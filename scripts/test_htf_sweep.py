from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import pandas as pd

from v17.common.types import Symbol, Side, TF
from v17.data.parquet_store import read_1m
from v17.config import get_settings
from v17.data.resample import resample
from v17.structure.swings import detect_swings

s = get_settings()
START = datetime(2018, 1, 1, tzinfo=UTC)
END = datetime(2018, 12, 31, 23, 59, tzinfo=UTC)

for sym_str in ["GBPUSD", "USATECHIDXUSD"]:
    sym = Symbol(sym_str)
    df = read_1m(sym, START, END, s.parquet_root)
    bars_1d = resample(df, TF.D1)
    
    # Calculate how often PDH or PDL is swept on intraday bars
    print(f"\nAnalyzing HTF Sweeps for {sym_str} in 2018 (bars_1d: {len(bars_1d)})...")
    
    # For each day, get PDH and PDL
    pdh_swept_count = 0
    pdl_swept_count = 0
    inside_days = 0
    
    for i in range(1, len(bars_1d)):
        prev_hi = bars_1d["high"].iloc[i - 1]
        prev_lo = bars_1d["low"].iloc[i - 1]
        cur_hi = bars_1d["high"].iloc[i]
        cur_lo = bars_1d["low"].iloc[i]
        
        swept_hi = cur_hi > prev_hi
        swept_lo = cur_lo < prev_lo
        
        if swept_hi and not swept_lo:
            pdh_swept_count += 1
        elif swept_lo and not swept_hi:
            pdl_swept_count += 1
        elif swept_hi and swept_lo:
            # Outside day (swept both)
            pdh_swept_count += 1
            pdl_swept_count += 1
        else:
            inside_days += 1
            
    print(f"Total Trading Days: {len(bars_1d) - 1}")
    print(f"Days sweeping PDH: {pdh_swept_count}")
    print(f"Days sweeping PDL: {pdl_swept_count}")
    print(f"Inside Days (no sweep of PDH/PDL): {inside_days}")
