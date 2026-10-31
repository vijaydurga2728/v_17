from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from v17.common.types import TF, Bias, RunId, Side, SignalId, Symbol, Ticket


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _require_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) != UTC.utcoffset(ts):
        raise ValueError("timestamp must be timezone-aware UTC")
    return ts


class Bar(_Frozen):
    symbol: Symbol
    tf: TF
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = 0
    spread_pips: Decimal = Decimal("0")

    @field_validator("ts")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)

    @model_validator(mode="after")
    def _ohlc_invariants(self) -> Bar:
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError("OHLC invariant violated")
        return self


class Tick(_Frozen):
    symbol: Symbol
    ts: datetime
    bid: Decimal
    ask: Decimal

    @field_validator("ts")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)

    @model_validator(mode="after")
    def _ask_ge_bid(self) -> Tick:
        if self.ask < self.bid:
            raise ValueError("ask must be >= bid")
        return self


class CalendarEvent(_Frozen):
    at: datetime
    currency: Literal["USD", "EUR", "GBP"]
    impact: Literal["high", "medium", "low"]
    title: str

    @field_validator("at")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)


class Zone(_Frozen):
    kind: Literal["fvg", "ob"]
    side: Side
    tf: TF
    created_at: datetime
    top: Decimal
    bottom: Decimal
    mitigated_at: datetime | None = None

    @field_validator("created_at")
    @classmethod
    def _created_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)

    @field_validator("mitigated_at")
    @classmethod
    def _mitigated_utc(cls, v: datetime | None) -> datetime | None:
        return None if v is None else _require_utc(v)

    @model_validator(mode="after")
    def _top_ge_bottom(self) -> Zone:
        if self.top < self.bottom:
            raise ValueError("top must be >= bottom")
        return self


class Swing(_Frozen):
    kind: Literal["bos", "choch", "mss"]
    side: Side
    tf: TF
    at: datetime
    price: Decimal

    @field_validator("at")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)


class Sweep(_Frozen):
    kind: Literal["bsl", "ssl"]
    tf: TF
    at: datetime
    level: Decimal

    @field_validator("at")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)


class StructureSnapshot(_Frozen):
    symbol: Symbol
    at: datetime
    bias: Bias
    zones: list[Zone]
    swings: list[Swing]
    sweeps: list[Sweep]

    @field_validator("at")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)


_REQUIRED_CONFLUENCE: frozenset[str] = frozenset({"bias", "fvg", "ob", "mss", "sweep"})
_MIN_RR = Decimal("1.5")


class Signal(_Frozen):
    id: SignalId
    symbol: Symbol
    setup: Literal["silver_bullet", "judas_swing"]
    side: Side
    at: datetime
    entry: Decimal
    sl: Decimal
    tp: Decimal
    rr: Decimal
    confluence: dict[str, bool]
    note: str = ""

    @field_validator("at")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)

    @model_validator(mode="after")
    def _validate(self) -> Signal:
        if self.rr < _MIN_RR:
            raise ValueError("rr must be >= 1.5")
        if frozenset(self.confluence.keys()) != _REQUIRED_CONFLUENCE:
            raise ValueError(f"confluence must have keys {sorted(_REQUIRED_CONFLUENCE)}")
        return self


class Fill(_Frozen):
    ticket: Ticket
    symbol: Symbol
    side: Side
    size_lots: Decimal
    at: datetime
    price: Decimal

    @field_validator("at")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)


class Trade(_Frozen):
    ticket: Ticket
    signal_id: SignalId
    symbol: Symbol
    side: Side
    size_lots: Decimal
    entry: Decimal
    sl: Decimal
    tp: Decimal
    opened_at: datetime
    closed_at: datetime | None = None
    close_price: Decimal | None = None
    pnl: Decimal | None = None
    reason: str = ""

    @field_validator("opened_at")
    @classmethod
    def _opened_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)

    @field_validator("closed_at")
    @classmethod
    def _closed_utc(cls, v: datetime | None) -> datetime | None:
        return None if v is None else _require_utc(v)


class AccountState(_Frozen):
    equity: Decimal
    balance: Decimal
    starting_equity: Decimal
    peak_equity: Decimal
    daily_realized_pnl: Decimal
    total_realized_pnl: Decimal
    best_day_pnl: Decimal
    open_positions: int
    trading_days_count: int
    is_locked_today: bool
    kill_active: bool
    trades_today: int = 0


class Decision(_Frozen):
    allow: bool
    reason: str
    code: (
        Literal[
            "ok",
            "news_blackout",
            "daily_stop_locked",
            "dd_guard",
            "consistency_rule",
            "max_positions",
            "max_trades_today",
            "rr_too_low",
            "sl_too_tight",
            "kill_active",
        ]
        | None
    ) = None
    size_lots: Decimal | None = None
    sl: Decimal | None = None
    tp: Decimal | None = None


class OrderRequest(_Frozen):
    symbol: Symbol
    side: Side
    size_lots: Decimal
    entry: Decimal | None = None
    sl: Decimal
    tp: Decimal
    comment: str = ""
    magic: int = 170000


class OrderResult(_Frozen):
    ok: bool
    ticket: Ticket | None = None
    filled_price: Decimal | None = None
    filled_at: datetime | None = None
    error_code: int | None = None
    error_message: str | None = None

    @field_validator("filled_at")
    @classmethod
    def _filled_utc(cls, v: datetime | None) -> datetime | None:
        return None if v is None else _require_utc(v)


class Position(_Frozen):
    ticket: Ticket
    symbol: Symbol
    side: Side
    size_lots: Decimal
    opened_at: datetime
    entry: Decimal
    sl: Decimal
    tp: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal

    @field_validator("opened_at")
    @classmethod
    def _opened_utc(cls, v: datetime) -> datetime:
        return _require_utc(v)


class BacktestConfig(_Frozen):
    symbol: Symbol
    start: datetime
    end: datetime
    starting_equity: Decimal = Decimal("10000")
    seed: int = 42
    setups: list[str] = ["silver_bullet", "judas_swing"]

    @field_validator("start", "end")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _require_utc(v)


class RunReport(_Frozen):
    run_id: RunId
    config: BacktestConfig
    trades: int
    winrate: float
    pf: float
    sharpe: float
    max_dd_pct: float
    net_pnl: Decimal
    oos_trades: int = 0
    oos_pf: float = 0.0
    oos_sharpe: float = 0.0
    oos_max_dd_pct: float = 0.0
    walkforward_folds_passed: int = 0
    mc_p5_pf: float = 0.0
    mc_p95_max_dd_pct: float = 0.0
