from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from v17.common.dtos import Zone
from v17.common.timeframes import tf_minutes
from v17.common.types import TF, Side
from v17.structure.atr import atr


def detect_obs(
    df_tf: pd.DataFrame,
    tf: TF,
    atr_mult: float = 2.0,
    max_age_bars: int = 30,
    lookback: int = 10,
) -> list[Zone]:
    out: list[Zone] = []
    df = df_tf.reset_index(drop=True)
    atr_series = atr(df, period=14).to_numpy()
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    ts = df["ts"].tolist()
    bar_dur = timedelta(minutes=tf_minutes(tf))
    for i in range(14, len(df)):
        body = abs(closes[i] - opens[i])
        if pd.isna(atr_series[i]) or atr_series[i] == 0:
            continue
        if body < atr_mult * atr_series[i]:
            continue
        bull_displacement = closes[i] > opens[i]
        confirmed_at = ts[i].to_pydatetime() + bar_dur
        for k in range(i - 1, max(-1, i - lookback), -1):
            opp = (closes[k] < opens[k]) if bull_displacement else (closes[k] > opens[k])
            if not opp:
                continue
            side = Side.BUY if bull_displacement else Side.SELL
            top = Decimal(str(max(opens[k], closes[k])))
            bottom = Decimal(str(min(opens[k], closes[k])))
            z = Zone(
                kind="ob",
                side=side,
                tf=tf,
                created_at=confirmed_at,
                top=top,
                bottom=bottom,
            )
            out.append(_apply_mitigation(z, closes, ts, i))
            break
    return out


def _apply_mitigation(
    z: Zone,
    closes: np.ndarray,
    ts: list[pd.Timestamp],
    confirmed_idx: int,
) -> Zone:
    top = float(z.top)
    bottom = float(z.bottom)
    for j in range(confirmed_idx + 1, len(closes)):
        if z.side == Side.BUY:
            if closes[j] < bottom:
                mit: datetime = ts[j].to_pydatetime()
                return z.model_copy(update={"mitigated_at": mit})
        else:
            if closes[j] > top:
                mit: datetime = ts[j].to_pydatetime()
                return z.model_copy(update={"mitigated_at": mit})
    return z
