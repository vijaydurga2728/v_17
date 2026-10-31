from __future__ import annotations

from typing import Protocol

from v17.common.dtos import RunReport


class ValidationGate(Protocol):
    def evaluate(self, report: RunReport) -> tuple[bool, list[str]]: ...

    def write_sentinel(self, report: RunReport) -> None: ...

    def revoke(self) -> None: ...
