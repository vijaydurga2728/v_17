from __future__ import annotations

from typing import Any


class V17Error(Exception):
    def __init__(self, msg: str, **ctx: Any) -> None:
        super().__init__(msg)
        self.ctx: dict[str, Any] = dict(ctx)


class V17ConfigError(V17Error): ...


class V17DataError(V17Error): ...


class V17StructureError(V17Error): ...


class V17GatewayError(V17Error): ...


class V17GatewayDisconnected(V17GatewayError): ...


class V17ValidationFailed(V17Error): ...


class V17KillSwitchActive(V17Error): ...


class V17FTMORuleViolation(V17Error): ...
