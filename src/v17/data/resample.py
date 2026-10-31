from __future__ import annotations

import pandas as pd

from v17.common.timeframes import pandas_offset
from v17.common.types import TF


def resample(df_1m: pd.DataFrame, tf: TF) -> pd.DataFrame:
    if tf == TF.M1:
        return df_1m.copy()
    offset = pandas_offset(tf)
    g = df_1m.set_index("ts").resample(offset, label="left", closed="left")
    out = pd.DataFrame(
        {
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "volume": g["volume"].sum(min_count=1),
            "spread_pips": g["spread_pips"].mean(),
        }
    ).dropna(subset=["open"]).reset_index()
    out["volume"] = out["volume"].astype("int64")
    return out
