"""Strict, frozen contracts for the cycle 23 event ledger and chart annotations (spec §4, §5)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Timeframe = Literal["D1", "15m", "5m", "1m"]
Category = Literal[
    "filled",
    "unfilled_expired",
    "rejected_after_sweep",
    "rejected_pre_sweep",
    "excluded",
]
Scalar = float | int | str | bool | None


class VisualEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    instrument: str
    trading_date: str
    seq: int
    stage: str
    event_time: datetime | None  # None for computed (untimed) stages
    available_at: datetime
    timeframe: Timeframe
    price: float | None = None
    rule_id: str
    confirmation_status: Literal["confirmed", "unconfirmed", "invalidated"]
    rejection_reason: str | None = None
    source_bar_ns: int | None = None  # start (or close, see stage) of the source candle/bar
    payload: dict[str, Scalar]
    data_fingerprint: str
    config_fingerprint: str
    engine_version: str


class DayRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument: str
    trading_date: str
    result: str  # "trade" or the engine's rejection reason
    category: Category
    charted: bool
    near_miss_stage: str | None  # frozen definition: swept + MSS, then failed one later stage
    cut_ns: int | None  # decision-time cut (charted days only)
    end_ns: int | None  # outcome-view end (charted days only)
    event_ids: tuple[str, ...]


class Annotation(BaseModel):
    """One drawable item. Times are UTC epoch ns; `available_ns` governs decision-view visibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    panel: Timeframe
    kind: Literal["hline", "box", "marker", "vspan"]
    label: str
    t0: int
    t1: int
    p0: float
    p1: float
    available_ns: int
    event_id: str
    outcome_only: bool = False
