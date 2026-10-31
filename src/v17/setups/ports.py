from __future__ import annotations

from datetime import datetime
from typing import Protocol

import pandas as pd

from v17.common.dtos import Signal, StructureSnapshot


class SetupEngine(Protocol):
    name: str

    def evaluate(
        self, snap: StructureSnapshot, now: datetime, bars_1m: pd.DataFrame
    ) -> Signal | None: ...
