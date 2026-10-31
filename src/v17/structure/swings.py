from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pandas as pd
from smartmoneyconcepts import smc

from v17.common.dtos import Swing
from v17.common.timeframes import tf_minutes
from v17.common.types import TF, Side
from v17.structure.smc_adapter import prepare_smc_df


def detect_swings(df_tf: pd.DataFrame, tf: TF, swing_length: int = 10) -> list[Swing]:
    smc_df = prepare_smc_df(df_tf)
    swings = smc.swing_highs_lows(smc_df, swing_length=swing_length)
    boschoch = smc.bos_choch(smc_df, swings)
    out: list[Swing] = []
    ts = df_tf["ts"].tolist()
    bar_dur = timedelta(minutes=tf_minutes(tf))
    for pos, row in enumerate(boschoch.itertuples(index=False)):
        bos = getattr(row, "BOS", None)
        choch = getattr(row, "CHOCH", None)
        level_val = getattr(row, "Level", None)
        broken_idx = getattr(row, "BrokenIndex", None)
        if bos is not None and pd.notna(bos):
            kind = "bos"
            side = Side.BUY if int(bos) == 1 else Side.SELL
        elif choch is not None and pd.notna(choch):
            kind = "choch"
            side = Side.BUY if int(choch) == 1 else Side.SELL
        else:
            continue
        if level_val is None or pd.isna(level_val):
            continue
        # Use BrokenIndex (the confirming break candle) if available; otherwise pos
        break_pos = int(broken_idx) if broken_idx is not None and pd.notna(broken_idx) else pos
        if break_pos >= len(ts):
            continue
        ts_val = ts[break_pos].to_pydatetime() if hasattr(ts[break_pos], "to_pydatetime") else ts[break_pos]
        at = ts_val + bar_dur
        out.append(
            Swing(
                kind=kind,
                side=side,
                tf=tf,
                at=at,
                price=Decimal(str(level_val)),
            )
        )
    return out
