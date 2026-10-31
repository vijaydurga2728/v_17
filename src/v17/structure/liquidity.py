from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pandas as pd
from smartmoneyconcepts import smc

from v17.common.dtos import Sweep
from v17.common.timeframes import tf_minutes
from v17.common.types import TF
from v17.structure.smc_adapter import prepare_smc_df


def detect_sweeps(df_tf: pd.DataFrame, tf: TF, swing_length: int = 10) -> list[Sweep]:
    smc_df = prepare_smc_df(df_tf)
    swings = smc.swing_highs_lows(smc_df, swing_length=swing_length)
    levels: list[tuple[int, float, int]] = []
    for pos, row in enumerate(swings.itertuples(index=False)):
        hl = getattr(row, "HighLow", None)
        if hl is None or pd.isna(hl):
            continue
        lvl = getattr(row, "Level", None)
        if lvl is None or pd.isna(lvl):
            continue
        levels.append((pos, float(lvl), int(hl)))
    out: list[Sweep] = []
    highs = df_tf["high"].to_numpy()
    lows = df_tf["low"].to_numpy()
    closes = df_tf["close"].to_numpy()
    ts = df_tf["ts"].tolist()
    bar_dur = timedelta(minutes=tf_minutes(tf))
    for pos, lvl_price, hl in levels:
        # A swing level at pos requires swing_length subsequent candles to confirm.
        start_j = pos + swing_length + 1
        for j in range(start_j, len(df_tf)):
            sweep_at = ts[j].to_pydatetime() + bar_dur
            if hl == 1:
                if highs[j] > lvl_price and closes[j] < lvl_price:
                    out.append(
                        Sweep(
                            kind="bsl",
                            tf=tf,
                            at=sweep_at,
                            level=Decimal(str(lvl_price)),
                        )
                    )
                    break
            elif lows[j] < lvl_price and closes[j] > lvl_price:
                out.append(
                    Sweep(
                        kind="ssl",
                        tf=tf,
                        at=sweep_at,
                        level=Decimal(str(lvl_price)),
                    )
                )
                break
    return out
