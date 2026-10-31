from __future__ import annotations

import pandas as pd
from smartmoneyconcepts import smc


def prepare_smc_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.set_index("ts")[["open", "high", "low", "close", "volume"]].copy()
    out = out.astype(
        {
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "int64",
        }
    )
    return out


def smc_swing_highs_lows(df: pd.DataFrame, swing_length: int = 10) -> pd.DataFrame:
    result: pd.DataFrame = smc.swing_highs_lows(df, swing_length=swing_length)
    return result
