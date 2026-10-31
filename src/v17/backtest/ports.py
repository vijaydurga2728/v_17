from __future__ import annotations

from typing import Protocol

from v17.common.dtos import BacktestConfig, RunReport


class Backtester(Protocol):
    def run(self, cfg: BacktestConfig) -> RunReport: ...
