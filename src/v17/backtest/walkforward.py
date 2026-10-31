from __future__ import annotations

from datetime import datetime, timedelta
from typing import TypedDict


class WFFold(TypedDict):
    is_start: datetime
    is_end: datetime
    oos_start: datetime
    oos_end: datetime


def anchored_folds(
    start: datetime, end: datetime, n_folds: int = 12, is_pct: float = 0.6
) -> list[WFFold]:
    total = (end - start).total_seconds()
    if total <= 0 or n_folds <= 0:
        return []
    fold_span = total / n_folds
    folds: list[WFFold] = []
    for i in range(n_folds):
        oos_end = start + timedelta(seconds=fold_span * (i + 1))
        is_end = start + timedelta(seconds=fold_span * (i + 1) * is_pct)
        oos_start = is_end
        if oos_start >= oos_end:
            continue
        folds.append(
            {
                "is_start": start,
                "is_end": is_end,
                "oos_start": oos_start,
                "oos_end": oos_end,
            }
        )
    return folds
