from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from v17.common.dtos import StructureSnapshot
from v17.common.errors import V17StructureError
from v17.common.types import TF, Symbol
from v17.structure.bias import compute_bias
from v17.structure.fvg import detect_fvgs
from v17.structure.liquidity import detect_sweeps
from v17.structure.mss import detect_mss
from v17.structure.ob import detect_obs
from v17.structure.swings import detect_swings

REQUIRED_TFS: tuple[TF, ...] = (TF.D1, TF.H4, TF.M15, TF.M1)


class DefaultStructureEngine:
    def __init__(self, symbol: Symbol) -> None:
        self.symbol = symbol

    def analyze(self, bars_by_tf: Mapping[TF, pd.DataFrame]) -> StructureSnapshot:
        for tf in REQUIRED_TFS:
            if tf not in bars_by_tf:
                raise V17StructureError("missing TF", tf=tf.value)
        df_1d = bars_by_tf[TF.D1]
        df_4h = bars_by_tf[TF.H4]
        df_15m = bars_by_tf[TF.M15]
        df_1m = bars_by_tf[TF.M1]
        bias = compute_bias(df_1d, df_4h)
        zones = detect_fvgs(df_15m, TF.M15) + detect_obs(df_15m, TF.M15)
        swings_4h = detect_swings(df_4h, TF.H4, swing_length=3)
        mss_1m = detect_mss(df_1m, zones)
        sweeps = detect_sweeps(df_15m, TF.M15, swing_length=10)
        at = df_1m["ts"].iloc[-1].to_pydatetime()
        return StructureSnapshot(
            symbol=self.symbol,
            at=at,
            bias=bias,
            zones=zones,
            swings=swings_4h + mss_1m,
            sweeps=sweeps,
        )
