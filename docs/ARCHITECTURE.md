# ARCHITECTURE — v17 ICT Trading System

Date: 2026-10-28
Spec: `docs/SPEC.md`

## 1. Design Approach

**Deep modules.** Each module (M1–M10) exposes a tiny `Protocol` interface; the behavior volume lives inside. Callers learn the interface once; the implementation can grow without widening the surface.

**Explicit seams.** Interfaces live at module edges only. Internal functions stay private. Two adapter rule: a seam exists only where two implementations actually exist (e.g., `MT5Gateway` real + `FakeMT5`).

**Deterministic + pure where possible.** M1–M6 are pure/deterministic. Side effects isolated to M7 (MT5), M8 (scheduler), M9 (I/O).

**Dependencies injected, never created.** Clock, config, logger, data source, gateway — all passed in. Enables test seams at every layer.

## 2. Module Diagram

```
┌────────────────── Config + CLI (M10) ─────────────────────┐
│                                                            │
│   ┌──── Data (M1) ─────────────────────────────────┐      │
│   │  CSVIngestor | ParquetStore | CalendarProvider │      │
│   └────────┬───────────────────────────────────────┘      │
│            │ Bar, Tick, CalendarEvent                      │
│   ┌────────▼──── Market Structure (M2) ────────────┐      │
│   │  FVGDetector | OBDetector | BOSDetector |      │      │
│   │  MSSDetector | LiquidityDetector | BiasEngine  │      │
│   └────────┬───────────────────────────────────────┘      │
│            │ Zone, Swing, Bias                             │
│   ┌────────▼──── Setup Engines (M3) ───────────────┐      │
│   │  SilverBullet | JudasSwing                     │──┐   │
│   └────────┬───────────────────────────────────────┘  │   │
│            │ Signal                                     │   │
│   ┌────────▼──── Risk Engine (M4) ─────────────────┐  │   │
│   │  PositionSizer | DailyGuard | DDGuard |        │  │   │
│   │  ConsistencyGuard | NewsBlackout               │  │   │
│   └────────┬───────────────────────────────────────┘  │   │
│            │ Decision                                   │   │
│   ┌────────▼──── Backtest (M5) ────────────────────┐  │   │
│   │  EventLoop | CostModel | WalkForward | MC      │  │   │
│   └────────┬───────────────────────────────────────┘  │   │
│            │ RunReport                                  │   │
│   ┌────────▼──── Validation Gate (M6) ─────────────┐  │   │
│   │  evaluate() → GATE_PASSED sentinel             │  │   │
│   └────────────────────────────────────────────────┘  │   │
│                                                        │   │
│   ┌────── MT5 Gateway (M7) ───────────────────────┐   │   │
│   │  MT5Gateway (real) | FakeMT5                  │◄──┘   │
│   │  single-thread + command queue                 │       │
│   └────────┬──────────────────────────────────────┘       │
│            │                                               │
│   ┌────────▼──── Live Runner (M8) ─────────────────┐      │
│   │  KillzoneScheduler | PreFlight | StateMachine  │      │
│   │  depends on M3+M4+M7                           │      │
│   └────────────────────────────────────────────────┘      │
│                                                            │
│   Observability (M9) — cross-cuts everything (log, SQLite, Telegram)│
└────────────────────────────────────────────────────────────┘
```

## 3. Seams (where interfaces live)

| Seam | Interface | Adapters | Why real seam |
|---|---|---|---|
| Data source | `BarProvider`, `TickProvider` | `ParquetBarProvider`, `MT5TickProvider`, `ReplayTickProvider` | Backtest vs live vs test |
| Execution gateway | `TradeGateway` | `MT5Gateway`, `FakeMT5` | Live vs test |
| Clock | `Clock` | `SystemClock`, `FrozenClock` | Deterministic tests |
| Calendar | `CalendarProvider` | `FFJsonCalendar`, `StaticCalendar` | Live vs backtest-fixture |
| Alerts | `Alerter` | `TelegramAlerter`, `NullAlerter` | Prod vs dev/test |
| State store | `StateStore` | `SQLiteStateStore`, `InMemoryStateStore` | Prod vs test |

Everything else is one implementation → no seam.

## 4. Deep Module Depth Check

For each module: *small interface, large implementation*.

### M2 Market Structure — depth = HIGH
```python
class StructureEngine(Protocol):
    def analyze(self, bars_by_tf: dict[TF, DataFrame]) -> StructureSnapshot: ...
```
One method. Caller passes multi-TF bars, gets a snapshot (bias, zones, swings, sweeps). Internally wraps `smartmoneyconcepts` + custom detectors.

### M3 Setup Engines — depth = HIGH
```python
class SetupEngine(Protocol):
    def evaluate(self, snap: StructureSnapshot, now: datetime) -> Signal | None: ...
```
One method per setup. Returns a signal or None.

### M4 Risk Engine — depth = HIGH
```python
class RiskEngine(Protocol):
    def check(self, signal: Signal, account: AccountState) -> Decision: ...
```
One method. Does sizing, daily guard, DD guard, consistency, news blackout — all behind one call.

### M5 Backtest — depth = HIGH
```python
class Backtester(Protocol):
    def run(self, cfg: BacktestConfig) -> RunReport: ...
```
One method. Orchestrates loop + cost model + walk-forward + MC internally.

### M7 MT5 Gateway — depth = HIGH, large adapter
```python
class TradeGateway(Protocol):
    def connect(self) -> None: ...
    def positions(self) -> list[Position]: ...
    def submit(self, order: OrderRequest) -> OrderResult: ...
    def modify(self, ticket: int, sl: Price, tp: Price) -> OrderResult: ...
    def close(self, ticket: int) -> OrderResult: ...
```
Five methods. Covers full lifecycle; underlying package complexity hidden.

### M8 Live Runner — depth = MEDIUM-HIGH
```python
class LiveRunner(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
```
Two methods. Scheduler + state machine inside.

## 5. Data Flow — Live Trade

```
APScheduler (06:50 London)
  │
  ▼
PreFlight (M8) — checks GATE_PASSED, MT5 connect, calendar fresh, no KILL
  │  OK
  ▼
Tick loop (M7 → M8) ───┐
  │                     │
  ▼                     │
Bar builder (1m, 15m)   │
  │                     │
  ▼                     │
StructureEngine.analyze (M2)
  │
  ▼
SetupEngine.evaluate × [SB, Judas] (M3) → Signal?
  │  Signal
  ▼
NewsBlackout.check (M4) ──reject──▶ log + skip
  │  allow
  ▼
RiskEngine.check (M4) → Decision{allow, size, sl, tp} ──reject──▶ log + skip
  │  allow
  ▼
TradeGateway.submit (M7) → OrderResult
  │
  ▼
Observability (M9) — log + SQLite + Telegram alert
  │
  ▼
State: ARMED → IN_TRADE
  │
  ▼
Position monitor (M8) — until SL/TP/close → MANAGED → CLOSED
```

## 6. Data Flow — Backtest Walk-Forward

```
CLI: v17 walkforward --symbol EURUSD --folds 12
  │
  ▼
Load 2014–2026 Parquet (M1)
  │
  ▼
Fold splitter: anchored IS/OOS (60/40) × 12
  │
  ▼
For each fold:
  ├─ Backtester.run on IS (optional param tuning OFF — rules are fixed)
  └─ Backtester.run on OOS → trades + equity
  │
  ▼
Aggregate fold reports → walkforward.json
  │
  ▼
MC: 500 trade-perm + 500 block-bootstrap (b=5) → montecarlo.json
  │
  ▼
ValidationGate.evaluate → GATE_PASSED / FAIL
  │
  ▼
Observability: equity curve PNG, metrics report
```

## 7. State Machine (Live Runner)

```
     ┌─────────┐
     │  IDLE   │◄──────────────┐
     └────┬────┘               │
          │ 06:50 London       │ CLOSED
          ▼                    │
     ┌─────────┐               │
     │ PRE-FLIGHT              │
     └────┬────┘               │
          │ OK                 │
          ▼                    │
     ┌─────────┐               │
     │  ARMED  │───Signal───┐  │
     └────┬────┘            │  │
          │ 10:05 London    │  │
          │ or KILL         │  │
          ▼                 ▼  │
     ┌─────────┐      ┌──────────┐
     │  IDLE   │      │ IN_TRADE │
     └─────────┘      └────┬─────┘
                           │
                           ▼
                      ┌──────────┐
                      │ MANAGED  │
                      └────┬─────┘
                           │ SL/TP/manual close
                           ▼
                      ┌──────────┐
                      │  CLOSED  │─────▶ back to ARMED or IDLE
                      └──────────┘
```

## 8. Concurrency Model

- **Single OS process.**
- **Main thread**: APScheduler + state machine.
- **MT5 thread** (M7): dedicated worker consuming command queue. All `MetaTrader5` calls happen here. Not thread-safe otherwise.
- **Observability thread** (M9): consumes a logging queue, writes to disk + Telegram.
- **No asyncio.** Keep simple. MT5 package is sync.

## 9. Storage Layout

```
data/
├── raw/                                # symlinks to Dukascopy CSVs
├── parquet/
│   ├── EURUSD/
│   │   ├── 1m/year=2014/*.parquet
│   │   ├── 15m/year=2014/*.parquet
│   │   └── ...
│   └── GBPUSD/
├── calendar/
│   └── 2026-W44.json
└── state/
    ├── GATE_PASSED            # sentinel; required for live
    ├── KILL                   # sentinel; stops live
    └── v17.sqlite             # trades, equity_daily, signals, errors

runs/
└── 2026-10-28_142300_eurusd_wf12/
    ├── config.toml
    ├── trades.parquet
    ├── equity.parquet
    ├── walkforward.json
    ├── montecarlo.json
    ├── metrics.json
    └── equity_curve.png
```

## 10. Error Taxonomy

| Class | Where | Behavior |
|---|---|---|
| `V17ConfigError` | M10 load | abort immediately |
| `V17DataError` | M1 ingest/validate | abort with context |
| `V17StructureError` | M2 | log + skip signal |
| `V17RiskRejected` | M4 | log reason + skip signal (NOT an error, a Decision) |
| `V17GatewayError` | M7 | retry 3× backoff; escalate |
| `V17GatewayDisconnected` | M7 | reconnect loop |
| `V17ValidationFailed` | M6 | exit 1, no GATE_PASSED |
| `V17KillSwitchActive` | M8 | halt + alert |
| `V17FTMORuleViolation` | M4 | emergency flat + alert + lock |

All errors structured, logged with context, surfaced via Telegram at `error` level.

## 11. Security + Secrets

- `.env` for `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`.
- `.env` in `.gitignore`.
- No secrets in logs; `structlog` processor masks keys matching `/password|token|secret/i`.
- SQLite file permissioned to user only (`chmod 600` equivalent on Windows).

## 12. Deployment

- No cloud. Runs on operator's Windows box.
- MT5 terminal must be running + logged in.
- Service wrapper: Windows Task Scheduler (preferred) or `nssm` as fallback.
- Autostart on boot; auto-restart on crash.
- Logs to `logs/`, rotated daily.

## 13. Observability Signals

- **Metrics** (daily report):
  - trades_count, winrate, pf, avg_rr, net_pnl, daily_pnl_pct, dd_pct, consistency_ratio.
- **Logs**: structured JSONL with `event`, `setup`, `signal_id`, `confluence_state`, `reason`.
- **Alerts** (Telegram):
  - entry, exit, daily soft stop, DD guard, FTMO rule warning, errors (crit), kill switch triggered.

## 14. Open Design Items

- Decision pending: single-pair vs dual-pair simultaneous backtest aggregation (locked single-pair per run; portfolio report in M9 merges results).
- No ML in MVP — regime classifier stays as explicit ADR future-work item.
