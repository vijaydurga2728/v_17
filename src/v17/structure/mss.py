from __future__ import annotations

from datetime import datetime

import pandas as pd

from v17.common.dtos import Swing, Zone
from v17.common.types import TF
from v17.structure.atr import atr
from v17.structure.swings import detect_swings


def _in_unmitigated_zone(price: float, zones: list[Zone], at: datetime | None = None) -> bool:
    for z in zones:
        if z.mitigated_at is not None and (at is None or z.mitigated_at <= at):
            continue
        if float(z.bottom) <= price <= float(z.top):
            return True
    return False


def detect_mss(
    df_1m: pd.DataFrame, zones_15m: list[Zone], atr_mult: float = 1.5
) -> list[Swing]:
    # ICT direction confirmation only. Zone-containment is a separate confluence
    # checked at setup level by `_pick_zone`. Keep ATR body filter as the
    # displacement signal.
    _ = zones_15m
    atr_series = atr(df_1m, period=14)
    choches = [s for s in detect_swings(df_1m, TF.M1, swing_length=10) if s.kind == "choch"]
    out: list[Swing] = []
    ts_index: dict[datetime, int] = {}
    for pos, t in enumerate(df_1m["ts"].tolist()):
        key = t.to_pydatetime() if hasattr(t, "to_pydatetime") else t
        ts_index[key] = pos
    opens = df_1m["open"].to_numpy()
    closes = df_1m["close"].to_numpy()
    for s in choches:
        idx = ts_index.get(s.at)
        if idx is None:
            continue
        body = abs(float(closes[idx]) - float(opens[idx]))
        a = atr_series.iloc[idx]
        if pd.isna(a) or body < atr_mult * a:
            continue
        out.append(Swing(kind="mss", side=s.side, tf=TF.M1, at=s.at, price=s.price))
    return out
