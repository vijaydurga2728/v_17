from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Alerter(Protocol):
    def send(self, message: str, level: str = "info") -> None: ...


class NullAlerter:
    def send(self, message: str, level: str = "info") -> None:
        pass
