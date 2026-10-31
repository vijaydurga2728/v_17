from __future__ import annotations

from enum import StrEnum


class RunnerState(StrEnum):
    IDLE = "idle"
    PRE_FLIGHT = "pre_flight"
    ARMED = "armed"
    IN_TRADE = "in_trade"
    MANAGED = "managed"
    CLOSED = "closed"
