from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

import pandas as pd

from v17.common.dtos import StructureSnapshot
from v17.common.types import TF


class StructureEngine(Protocol):
    def analyze(self, bars_by_tf: Mapping[TF, pd.DataFrame]) -> StructureSnapshot: ...
