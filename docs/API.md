# API — Interfaces & Domain Model

Date: 2026-10-28
Spec: `docs/SPEC.md`
Architecture: `docs/ARCHITECTURE.md`

All interfaces defined as `typing.Protocol`. Keeps modules deep: one method per Protocol typical, DTOs are flat Pydantic models.

## 1. Common Types

```python
# src/v17/common/types.py
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal, NewType
from pydantic import BaseModel, Field

# Branded ID types prevent mix-ups
Symbol = NewType("Symbol", str)        # "EURUSD" | "GBPUSD"
Ticket = NewType("Ticket", int)        # MT5 position ticket
SignalId = NewType("SignalId", str)
RunId = NewType("RunId", str)

Price = Decimal  # exact pip precision
Lots = Decimal

class TF(str, Enum):
    M1 = "1m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

class Bias(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    NONE = "none"
```

## 2. Market Data DTOs

```python
# src/v17/common/dtos.py

class Bar(BaseModel):
    symbol: Symbol
    tf: TF
    ts: datetime        # UTC, bar open time
    open: Price
    high: Price
    low: Price
    close: Price
    volume: int = 0
    spread_pips: Decimal = Decimal("0")

class Tick(BaseModel):
    symbol: Symbol
    ts: datetime        # UTC
    bid: Price
    ask: Price

class Zone(BaseModel):
    kind: Literal["fvg", "ob"]
    side: Side          # bullish → buy-side zone
    tf: TF
    created_at: datetime
    top: Price
    bottom: Price
    mitigated_at: datetime | None = None

class Swing(BaseModel):
    kind: Literal["bos", "choch"]
    side: Side
    tf: TF
    at: datetime
    price: Price

class Sweep(BaseModel):
    kind: Literal["bsl", "ssl"]
    tf: TF
    at: datetime
    level: Price

class StructureSnapshot(BaseModel):
    symbol: Symbol
    at: datetime
    bias: Bias
    zones: list[Zone]
    swings: list[Swing]
    sweeps: list[Sweep]

class Signal(BaseModel):
    id: SignalId
    symbol: Symbol
    setup: Literal["silver_bullet", "judas_swing"]
    side: Side
    at: datetime
    entry: Price
    sl: Price
    tp: Price
    rr: Decimal
    confluence: dict[str, bool]  # {"fvg": True, "ob": True, "mss": True, "sweep": True}
    note: str = ""

class CalendarEvent(BaseModel):
    at: datetime        # UTC
    currency: Literal["USD", "EUR", "GBP"]
    impact: Literal["high", "medium", "low"]
    title: str
```

## 3. Account & Risk DTOs

```python
class AccountState(BaseModel):
    equity: Decimal
    balance: Decimal
    starting_equity: Decimal          # for DD calc
    peak_equity: Decimal
    daily_realized_pnl: Decimal       # today
    total_realized_pnl: Decimal
    best_day_pnl: Decimal
    open_positions: int
    trading_days_count: int
    is_locked_today: bool             # soft daily stop hit
    kill_active: bool

class Decision(BaseModel):
    allow: bool
    reason: str                       # human-readable
    code: Literal[
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
    ] | None = None
    size_lots: Lots | None = None
    sl: Price | None = None
    tp: Price | None = None
```

## 4. Execution DTOs

```python
class OrderRequest(BaseModel):
    symbol: Symbol
    side: Side
    size_lots: Lots
    entry: Price | None               # None = market
    sl: Price
    tp: Price
    comment: str = ""
    magic: int = 170000               # bot identifier

class OrderResult(BaseModel):
    ok: bool
    ticket: Ticket | None
    filled_price: Price | None
    filled_at: datetime | None
    error_code: int | None
    error_message: str | None

class Position(BaseModel):
    ticket: Ticket
    symbol: Symbol
    side: Side
    size_lots: Lots
    opened_at: datetime
    entry: Price
    sl: Price
    tp: Price
    current_price: Price
    unrealized_pnl: Decimal
```

## 5. Interfaces (Protocols)

### M1 — Data
```python
# src/v17/data/ports.py
class BarProvider(Protocol):
    def bars(self, symbol: Symbol, tf: TF, start: datetime, end: datetime) -> Iterable[Bar]: ...

class TickProvider(Protocol):
    def ticks(self, symbol: Symbol) -> Iterator[Tick]: ...   # live stream OR replay

class CalendarProvider(Protocol):
    def events(self, start: datetime, end: datetime) -> list[CalendarEvent]: ...
    def is_blackout(self, symbol: Symbol, at: datetime, window_min: int = 5) -> bool: ...
```

### M2 — Market Structure
```python
# src/v17/structure/ports.py
class StructureEngine(Protocol):
    def analyze(self, bars_by_tf: Mapping[TF, pd.DataFrame]) -> StructureSnapshot: ...
```

### M3 — Setup Engines
```python
# src/v17/setups/ports.py
class SetupEngine(Protocol):
    name: str
    def evaluate(self, snap: StructureSnapshot, now: datetime) -> Signal | None: ...
```

### M4 — Risk Engine
```python
# src/v17/risk/ports.py
class RiskEngine(Protocol):
    def check(self, signal: Signal, account: AccountState) -> Decision: ...
    def on_fill(self, trade: Trade, account: AccountState) -> AccountState: ...
    def on_close(self, trade: Trade, account: AccountState) -> AccountState: ...
```

### M5 — Backtest
```python
# src/v17/backtest/ports.py
class BacktestConfig(BaseModel):
    symbol: Symbol
    start: datetime
    end: datetime
    starting_equity: Decimal = Decimal("100000")
    seed: int = 42
    setups: list[str] = ["silver_bullet", "judas_swing"]

class RunReport(BaseModel):
    run_id: RunId
    config: BacktestConfig
    trades: int
    winrate: float
    pf: float
    sharpe: float
    max_dd_pct: float
    net_pnl: Decimal
    oos_trades: int
    oos_pf: float
    oos_sharpe: float
    oos_max_dd_pct: float
    walkforward_folds_passed: int
    mc_p5_pf: float
    mc_p95_max_dd_pct: float

class Backtester(Protocol):
    def run(self, cfg: BacktestConfig) -> RunReport: ...
```

### M6 — Validation Gate
```python
# src/v17/validation/ports.py
class ValidationGate(Protocol):
    def evaluate(self, report: RunReport) -> tuple[bool, list[str]]:
        """Returns (passed, failure_reasons)."""
    def write_sentinel(self, report: RunReport) -> None: ...   # GATE_PASSED
    def revoke(self) -> None: ...                              # delete sentinel
```

### M7 — Trade Gateway
```python
# src/v17/mt5/ports.py
class TradeGateway(Protocol):
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    def symbol_select(self, symbol: Symbol) -> None: ...
    def rates(self, symbol: Symbol, tf: TF, count: int) -> list[Bar]: ...
    def tick(self, symbol: Symbol) -> Tick: ...
    def positions(self) -> list[Position]: ...
    def submit(self, req: OrderRequest) -> OrderResult: ...
    def modify(self, ticket: Ticket, sl: Price, tp: Price) -> OrderResult: ...
    def close(self, ticket: Ticket) -> OrderResult: ...
```

### M8 — Live Runner
```python
# src/v17/live/ports.py
class LiveRunner(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def status(self) -> dict[str, Any]: ...
```

### M9 — Observability
```python
# src/v17/obs/ports.py
class Alerter(Protocol):
    def send(self, level: Literal["info", "warn", "error", "crit"], msg: str, **ctx: Any) -> None: ...

class StateStore(Protocol):
    def record_trade(self, trade: Trade) -> None: ...
    def update_equity(self, when: datetime, equity: Decimal) -> None: ...
    def recent_trades(self, days: int) -> list[Trade]: ...
    def account_state(self) -> AccountState: ...

class Clock(Protocol):
    def now(self) -> datetime: ...                          # UTC
    def now_in(self, tz: str) -> datetime: ...
```

## 6. Error Contract

All domain errors raise typed exceptions from `v17.common.errors`:

```python
class V17Error(Exception):
    def __init__(self, msg: str, **ctx: Any): ...

class V17ConfigError(V17Error): ...
class V17DataError(V17Error): ...
class V17StructureError(V17Error): ...
class V17GatewayError(V17Error): ...
class V17GatewayDisconnected(V17GatewayError): ...
class V17ValidationFailed(V17Error): ...
class V17KillSwitchActive(V17Error): ...
class V17FTMORuleViolation(V17Error): ...
```

`V17RiskRejected` is **not** raised — it is a `Decision` returned.

## 7. CLI Contract

```
v17 ingest [--symbol SYM] [--force]
v17 ingest-calendar [--week YYYY-WW]
v17 backtest --symbol SYM --from YYYY-MM-DD --to YYYY-MM-DD [--seed N]
v17 walkforward --symbol SYM [--folds 12] [--seed N]
v17 montecarlo --run RUN_ID [--perm 500] [--block 500] [--block-size 5]
v17 validate --run RUN_ID            # exit 0=pass, 1=fail
v17 paper                            # FakeMT5 live loop
v17 live [--dry-run]                 # requires GATE_PASSED
v17 report [--day today|YYYY-MM-DD]
v17 kill                             # write KILL sentinel
v17 unkill                           # delete KILL (manual)
```

## 8. Backward Compatibility

- Internal interfaces only. No external consumers.
- Any Protocol change ships with an ADR + all adapters updated in the same commit.
- DTOs follow additive rule: new fields optional with defaults; no renames; removals require ADR.
