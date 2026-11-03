from __future__ import annotations

from datetime import UTC, datetime
import pandas as pd

from v17.common.types import Symbol, TF
from v17.data.parquet_store import read_1m
from v17.config import get_settings
from v17.data.resample import resample
from v17.structure.liquidity import detect_sweeps

s = get_settings()
START = datetime(2018, 1, 1, tzinfo=UTC)
END = datetime(2018, 12, 31, 23, 59, tzinfo=UTC)

for sym_str in ["EURUSD", "GBPUSD", "USATECHIDXUSD"]:
    sym = Symbol(sym_str)
    df = read_1m(sym, START, END, s.parquet_root)
    bars_15m = resample(df, TF.M15)
    sweeps_10 = detect_sweeps(bars_15m, TF.M15, swing_length=10)
    sweeps_3 = detect_sweeps(bars_15m, TF.M15, swing_length=3)
    sweeps_5 = detect_sweeps(bars_15m, TF.M15, swing_length=5)
    print(f"{sym_str}: 15m sweeps with length=10: {len(sweeps_10)}, length=5: {len(sweeps_5)}, length=3: {len(sweeps_3)}")
