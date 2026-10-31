from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from v17.common.dtos import Bar
from v17.common.types import TF, Symbol
from v17.data.parquet_store import read_1m
from v17.data.resample import resample


class ParquetBarProvider:
    def __init__(self, parquet_root: Path) -> None:
        self.parquet_root = parquet_root

    def bars(
        self, symbol: Symbol, tf: TF, start: datetime, end: datetime
    ) -> Iterable[Bar]:
        df = read_1m(symbol, start, end, self.parquet_root)
        if df.empty:
            return
        if tf != TF.M1:
            df = resample(df, tf)
            df = df[(df["ts"] >= pd.Timestamp(start)) & (df["ts"] <= pd.Timestamp(end))]
        for row in df.itertuples(index=False):
            # Mid-OHLC from independent bid/ask ticks can violate OHLC invariant
            # at the price-level; clamp high/low to envelope open/close.
            o = float(row.open)
            h = float(row.high)
            lo = float(row.low)
            c = float(row.close)
            h = max(h, o, c)
            lo = min(lo, o, c)
            yield Bar(
                symbol=symbol,
                tf=tf,
                ts=row.ts.to_pydatetime(),
                open=Decimal(str(o)),
                high=Decimal(str(h)),
                low=Decimal(str(lo)),
                close=Decimal(str(c)),
                volume=int(row.volume),
                spread_pips=Decimal(str(row.spread_pips)),
            )
