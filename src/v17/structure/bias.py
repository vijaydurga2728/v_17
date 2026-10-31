from __future__ import annotations

from decimal import Decimal

import pandas as pd

from v17.common.types import TF, Bias, Side
from v17.structure.swings import detect_swings

EMA_PERIOD = 20


def compute_bias_fast(
    ema20_at: Decimal, last_close: Decimal, last_4h_swing_side: Side | None
) -> Bias:
    if last_4h_swing_side is None:
        return Bias.NONE
    daily_bull = last_close > ema20_at
    four_h_bull = last_4h_swing_side == Side.BUY
    if daily_bull and four_h_bull:
        return Bias.BULL
    if (not daily_bull) and (not four_h_bull):
        return Bias.BEAR
    return Bias.NONE


def compute_bias(df_1d: pd.DataFrame, df_4h: pd.DataFrame) -> Bias:
    if len(df_1d) < EMA_PERIOD or len(df_4h) < EMA_PERIOD:
        return Bias.NONE
    ema20 = df_1d["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
    last_close = float(df_1d["close"].iloc[-1])
    daily_bull = last_close > float(ema20.iloc[-1])

    swings_4h = detect_swings(df_4h, TF.H4, swing_length=3)
    if not swings_4h:
        return Bias.NONE
    last_4h = swings_4h[-1]
    four_h_bull = last_4h.side == Side.BUY

    if daily_bull and four_h_bull:
        return Bias.BULL
    if (not daily_bull) and (not four_h_bull):
        return Bias.BEAR
    return Bias.NONE
