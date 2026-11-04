from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TypedDict

import pandas as pd


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


# =============================================================================
# SB 7-fold anchored walk-forward (spec section 6.2)
# =============================================================================


@dataclass(frozen=True)
class Fold:
    fold_id: int
    train_start: int
    train_end: int
    oos_start: int
    oos_end: int


def generate_folds() -> list[Fold]:
    train_start = pd.Timestamp("2015-01-01", tz="UTC").value
    out: list[Fold] = []
    for i in range(7):
        train_end_year = 2017 + i
        oos_year = 2018 + i
        train_end = pd.Timestamp(f"{train_end_year}-12-31 23:59:59", tz="UTC").value
        oos_start = pd.Timestamp(f"{oos_year}-01-01", tz="UTC").value
        oos_end = pd.Timestamp(f"{oos_year + 1}-01-01", tz="UTC").value
        out.append(Fold(
            fold_id=i + 1,
            train_start=train_start,
            train_end=train_end,
            oos_start=oos_start,
            oos_end=oos_end,
        ))
    return out
