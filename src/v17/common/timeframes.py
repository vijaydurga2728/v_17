from __future__ import annotations

from v17.common.types import TF

_OFFSET: dict[TF, str] = {TF.M1: "1min", TF.M5: "5min", TF.M15: "15min", TF.H1: "1h", TF.H4: "4h", TF.D1: "1D"}
_MINS: dict[TF, int] = {TF.M1: 1, TF.M5: 5, TF.M15: 15, TF.H1: 60, TF.H4: 240, TF.D1: 1440}
TF_ORDER: tuple[TF, ...] = (TF.M1, TF.M5, TF.M15, TF.H1, TF.H4, TF.D1)


def pandas_offset(tf: TF) -> str:
    return _OFFSET[tf]


def tf_minutes(tf: TF) -> int:
    return _MINS[tf]
