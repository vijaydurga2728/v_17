from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from v17.common.dtos import Zone
from v17.common.timeframes import tf_minutes
from v17.common.types import TF, Side


def detect_fvgs(df_tf: pd.DataFrame, tf: TF, max_age_bars: int = 30) -> list[Zone]:
    out: list[Zone] = []
    df = df_tf.reset_index(drop=True)
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    ts = df["ts"].tolist()
    bar_dur = timedelta(minutes=tf_minutes(tf))
    n = len(df)
    for i in range(2, n):
        confirmed_at = ts[i].to_pydatetime() + bar_dur
        if lows[i] > highs[i - 2]:
            top = Decimal(str(lows[i]))
            bottom = Decimal(str(highs[i - 2]))
            z = Zone(
                kind="fvg",
                side=Side.BUY,
                tf=tf,
                created_at=confirmed_at,
                top=top,
                bottom=bottom,
            )
            out.append(_apply_mitigation(z, highs, lows, ts, i))
        elif highs[i] < lows[i - 2]:
            top = Decimal(str(lows[i - 2]))
            bottom = Decimal(str(highs[i]))
            z = Zone(
                kind="fvg",
                side=Side.SELL,
                tf=tf,
                created_at=confirmed_at,
                top=top,
                bottom=bottom,
            )
            out.append(_apply_mitigation(z, highs, lows, ts, i))
    return out


def _apply_mitigation(
    z: Zone,
    highs: np.ndarray,
    lows: np.ndarray,
    ts: list[pd.Timestamp],
    confirmed_idx: int,
) -> Zone:
    top = float(z.top)
    bottom = float(z.bottom)
    # Check mitigation from the candle immediately following the confirmed 3-bar pattern
    for j in range(confirmed_idx + 1, len(highs)):
        if lows[j] <= top and highs[j] >= bottom:
            mit: datetime = ts[j].to_pydatetime()
            return z.model_copy(update={"mitigated_at": mit})
    return z
