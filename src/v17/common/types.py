from __future__ import annotations

from enum import StrEnum
from typing import NewType

Symbol = NewType("Symbol", str)
Ticket = NewType("Ticket", int)
SignalId = NewType("SignalId", str)
RunId = NewType("RunId", str)


class TF(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class Bias(StrEnum):
    BULL = "bull"
    BEAR = "bear"
    NONE = "none"


SUPPORTED_SYMBOLS: tuple[Symbol, ...] = (
    Symbol("EURUSD"),
    Symbol("GBPUSD"),
    Symbol("EURGBP"),
    Symbol("USDJPY"),
    Symbol("USATECHIDXUSD"),
)
