from __future__ import annotations

import pandas as pd

from v17.backtest.fast_choch import detect_choch_fast
from v17.common.dtos import Swing


def precompute_daily_ema20(bars_1d: pd.DataFrame) -> pd.Series:
    ema = bars_1d["close"].ewm(span=20, adjust=False).mean()
    return pd.Series(ema.to_numpy(), index=pd.to_datetime(bars_1d["ts"]), name="ema20")


def precompute_1m_choches(bars_1m: pd.DataFrame) -> list[Swing]:
    return detect_choch_fast(bars_1m, swing_window=10)
