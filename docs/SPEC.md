# SPEC — ICT/SMC Intraday Trading System for FTMO

**Project**: `v_17` (ICT algo bot)
**Author**: Vijayakumar R
**Date**: 2026-10-28
**Status**: Draft v1 (awaiting user approval)
**Prior docs**: `docs/research/SYNTHESIS.md`, `docs/research/deep-research.md`, `docs/research/agent-reach.md`, `docs/research/last30days.md`, `docs/research/find-skills.md`.

---

## 1. Objective

Build a fully-automated, deterministic, risk-governed intraday trading system that trades EURUSD + GBPUSD during the London killzone using ICT concepts (Silver Bullet + Judas Swing with FVG + MSS + Order Block + Liquidity Sweep confluence), passes a strict backtest + walk-forward + Monte Carlo validation gate, and runs live on an FTMO Challenge $100k account via MetaTrader 5.

**Success = validation gate pass + FTMO Challenge Phase 1 pass + Phase 2 pass + funded.**
**Failure = backtest fails gate → system is honestly declared not profitable. No curve fitting to force a pass.**

## 2. Users

- **Primary**: single operator (project owner). Local Windows machine, MT5 terminal.
- **No multi-user, no customer, no web UI, no SaaS.**

## 3. Non-Goals

- No ML / neural / RL models.
- No instruments beyond EURUSD + GBPUSD.
- No sessions beyond London killzone (02:00–05:00 NY / 07:00–10:00 London).
- No stocks, crypto, options, futures.
- No cloud deploy. Runs on operator's Windows box next to MT5.
- No Vercel / Next.js / web app.
- No manual trade override of risk engine.
- No copy-trading, grid, martingale, latency arb, HFT.

## 4. Capability Map (approved 2026-10-28)

```
M1 Data ─▶ M2 Market Structure ─▶ M3 Setup Engines ─┐
                                                     ├─▶ M5 Backtest ─▶ M6 Validation Gate ─▶ [LIVE UNLOCK]
                                   M4 Risk Engine ───┘
M7 MT5 Gateway ─▶ M8 Live Runner (needs M3, M4) ─────▶ Runtime
M9 Observability — cross-cut (logs/metrics/alerts/plots/reports)
M10 Config + CLI — top-level entrypoints
```

Build order: **M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10** (M9 slotted alongside M5+M8).

## 5. Domain Glossary (ICT/SMC)

Formal, unambiguous definitions. Pick ONE definition per concept and never mix.

| Term | Definition (locked) |
|---|---|
| **FVG (Fair Value Gap)** | 3-bar imbalance. Bullish: `low[i] > high[i-2]`. Bearish: `high[i] < low[i-2]`. Zone = [high[i-2], low[i]] (bullish) or [high[i], low[i-2]] (bearish). Unmitigated if price has not re-entered the zone. |
| **OB (Order Block)** | Last opposite-color candle before a displacement move that creates an FVG. Displacement = next-candle body ≥ 2.0×ATR(14). Zone = full body of the OB candle. Validity: unmitigated AND age ≤ 30 bars on its TF. |
| **BOS (Break of Structure)** | Price closes beyond prior HH (bullish) or LL (bearish) swing confirmed by `smartmoneyconcepts.swing_highs_lows` with window=10. Continuation signal. |
| **CHoCH (Change of Character)** | First BOS in opposite direction after a trend. Trend-reversal signal. |
| **MSS (Market Structure Shift)** | On 1m: a CHoCH that occurs INSIDE a 15m FVG or OB zone AND is backed by a candle whose body > 1.5×ATR(14). Our 1m entry trigger. |
| **BSL (Buy-Side Liquidity)** | Equal highs or prior swing high above current price. Target for shorts; sweep thereof is bearish setup trigger. |
| **SSL (Sell-Side Liquidity)** | Equal lows or prior swing low below current price. Target for longs; sweep thereof is bullish setup trigger. |
| **Liquidity Sweep** | Price prints a wick beyond BSL/SSL AND closes back inside the prior range on the TF being evaluated (15m for our setups). |
| **HTF Bias** | Direction of trend on Daily AND 4H. Bullish if last 4H structure = BOS up AND Daily close > Daily 20-EMA. Bearish if symmetric. Else NO BIAS → skip the day. |
| **London Killzone** | 02:00–05:00 America/New_York (DST-aware), equivalently 07:00–10:00 Europe/London. UTC varies with DST; store UTC, convert for display. |
| **Silver Bullet (SB)** | ICT setup. Window: 03:00–04:00 NY. Rules: HTF bias set; liquidity sweep of prior session high (shorts) or low (longs) occurred within 2h before window; price enters an unmitigated 15m FVG inside OB zone during window; 1m MSS confirms; enter market or limit at FVG mid; SL above/below OB; TP at next opposite-side liquidity, min 1:1.5 RR. |
| **Judas Swing** | ICT setup. Window: London open 07:00–08:30 London. Rules: HTF bias set; price sweeps Asian session high/low (Asian = 19:00–02:00 NY prev day) with wick + close back inside; 1m MSS confirms reversal into HTF bias direction; enter at MSS retrace to 15m FVG/OB mid; SL beyond sweep extreme; TP next liquidity, min 1:1.5 RR. |
| **ATR** | Average True Range, Wilder, 14 periods, computed on the TF in question. |
| **PF (Profit Factor)** | gross wins / gross losses. |
| **DD (Drawdown)** | peak-to-trough equity drop, % of peak. |
| **Max DD** | largest DD over the equity curve. |
| **Walk-Forward Anchored** | IS window starts at t0, grows by step; OOS window = next step. 12 folds across 2014–2026 data. |
| **Monte Carlo Hybrid** | 500 trade-order permutations (reshuffle P&L sequence) + 500 block-bootstrap (block=5, resample contiguous trade blocks). Preserves streak clustering. |
| **FTMO Consistency Rule** | (effective 2026-10-12) Best single trading day P&L ≤ 30% of total profit over the challenge. |

## 6. Quality Bar & Constraints

### 6.1 Hard constraints (never relaxable)
- **No live/demo `order_send` until validation gate green.** Enforced by `M6` writing a `GATE_PASSED` sentinel file consumed by `M8`.
- **No manual risk override.** Risk engine is pure, deterministic, reproducible.
- **No parameter curve-fitting past gate.** If gate fails on OOS, document failure and stop. Only re-attempt after a new hypothesis is written and justified in `docs/decisions/`.
- **UTC canonical for all timestamps in storage.** Timezone conversion only at display/scheduler boundary.
- **FTMO rule constants live in exactly one file**: `src/v17/risk/ftmo_rules.py`.

### 6.2 Validation gate thresholds (OOS, all must hold)
- PF ≥ 1.8
- Sharpe ≥ 2.0 (annualized, 252 trading days)
- Max DD < 6% of starting equity
- Winrate ≥ 50%
- MC 5th-percentile PF ≥ 1.3
- MC 95th-percentile max DD ≤ 8% (FTMO 10% − 2% buffer)
- ≥ 200 OOS trades
- ≥ 4 OOS folds pass individually (12-fold walk-forward)

### 6.3 FTMO rule constants (locked, 2026-10)
```
FTMO_CHALLENGE_100K = {
  "account_size": 100_000,
  "profit_target_phase1_pct": 10.0,
  "profit_target_phase2_pct": 5.0,
  "max_daily_loss_pct": 5.0,
  "soft_daily_stop_pct": 4.0,   # auto-flat + lockout
  "max_overall_dd_pct": 10.0,
  "min_trading_days": 4,
  "consistency_best_day_pct_of_profit": 30.0,
  "news_trading_allowed": True,  # we blackout anyway
  "weekend_hold_allowed": True,
  "ea_allowed": True,
  "forbidden": ["HFT", "grid", "martingale", "copy", "latency_arb"],
}
```

### 6.4 Risk constants
```
RISK = {
  "per_trade_pct": 1.0,          # of current equity
  "min_rr": 1.5,
  "max_concurrent_positions": 1, # one symbol at a time, portfolio-wide
  "max_trades_per_day": 3,
  "symbols": ["EURUSD", "GBPUSD"],
}
```

### 6.5 Cost model (backtest)
```
COST = {
  "EURUSD": {"spread_pips": 0.8, "slippage_pips_per_side": 0.3, "commission_per_lot": 0.0},
  "GBPUSD": {"spread_pips": 1.2, "slippage_pips_per_side": 0.3, "commission_per_lot": 0.0},
}
```

### 6.6 Performance
- Full 12-year backtest on both pairs: ≤ 15 min wall clock on operator's machine.
- Live tick→signal→order round-trip: ≤ 500 ms p95.
- MT5 reconnect: ≤ 10 s on disconnect.

### 6.7 Testing
- Unit coverage ≥ 85% on M1–M6 (deterministic modules).
- M7 covered via `FakeMT5` + contract tests.
- M8 integration tested with `FakeMT5` + replayed 1m bars; smoke-run entire killzone end-to-end.
- Regression test suite: lock golden backtest P&L on a fixed seed + fixed data snapshot. CI fails on drift.

### 6.8 Observability
- Every order attempt logged structured JSONL (symbol, side, size, SL, TP, reason, setup, confluence state).
- Every rejection logged with code + why.
- SQLite tables: `trades`, `equity_daily`, `signals`, `errors`.
- Telegram alerts: entry, exit, SL hit, TP hit, daily soft stop, DD guard trip, errors (crit level).
- Daily report at 22:00 operator time: trades, P&L, DD, FTMO rule status.

### 6.9 Boundaries (always / ask / never)

**Always**
- Run tests before any commit touching risk, backtest, or MT5 gateway.
- Validate ingested CSVs against schema + monotonic timestamps.
- Write a decision note (`docs/decisions/NNNN-<slug>.md`) for any constant change.
- UTC in storage.

**Ask first**
- Any change to risk constants, cost model, validation thresholds.
- Any new instrument.
- Any dependency add.
- Any Monte Carlo/walk-forward parameter change.
- Any FTMO rule constant edit.

**Never**
- Never bypass the validation gate.
- Never commit secrets (MT5 login, Telegram token, FTMO account creds). Use `.env` + `.gitignore`.
- Never log raw credentials.
- Never let a backtest "pass" by narrowing OOS window.
- Never ship without `GATE_PASSED` sentinel.

## 7. Per-Module Acceptance Criteria

### M1 — Data
- [ ] Ingest Dukascopy CSVs from `C:/Users/Vijayakumar R/Documents/` (EURUSD + GBPUSD, 2014–2026, bid + ask).
- [ ] Stitch 2014-2015 and 2015-2026 files; dedupe on timestamp.
- [ ] Build `mid = (bid+ask)/2`, keep `spread = ask-bid`.
- [ ] Store as Parquet partitioned by `symbol`/`year`.
- [ ] Resample to 15m, 1h, 4h, 1d from 1m with correct OHLC aggregation.
- [ ] UTC canonical; convert to America/New_York for killzone filter.
- [ ] FF calendar fetcher: pull JSON feed weekly, cache `data/calendar/YYYY-WW.json`; historical backfill via archived GitHub dumps.
- [ ] Blackout window generator: ±5 min around high-impact USD/EUR/GBP events.
- [ ] 100% schema validation on load; fail loud.

### M2 — Market Structure Engine
- [ ] Wrap `smartmoneyconcepts` (joshyattridge) under `src/v17/structure/`.
- [ ] FVG detector with glossary rule. Returns zones with `created_at`, `mitigated_at`, `tf`.
- [ ] OB detector with 2.0×ATR displacement rule.
- [ ] BOS/CHoCH detector with swing window=10.
- [ ] MSS detector (1m, inside 15m FVG/OB, body > 1.5×ATR).
- [ ] Liquidity (BSL/SSL) + sweep detector.
- [ ] HTF bias function (Daily+4H).
- [ ] All detectors deterministic + pure. Property-based tests.

### M3 — Setup Engines
- [ ] Silver Bullet: window + bias + sweep + FVG+OB + MSS → `Signal{side, entry, sl, tp, rr, setup_id}`.
- [ ] Judas Swing: Asian range + sweep + MSS + retrace → `Signal`.
- [ ] Reject signals with RR < 1.5 or SL distance < min stop.
- [ ] One Signal object per setup trigger; no mutation.
- [ ] 100% unit tested with hand-crafted fixtures from `SrsBlack/ict-knowledge-library` canonical examples.

### M4 — Risk Engine
- [ ] Position sizer: lots = f(equity, per_trade_pct, stop_distance_pips, pip_value).
- [ ] Daily P&L accumulator; soft stop at −4%, lockout rest of day.
- [ ] Overall DD guard at −10% (kill switch, write `KILL` sentinel).
- [ ] Consistency rule check: skip entry if (today_realized + est_win) / total_profit > 30%.
- [ ] Min trading days counter.
- [ ] All checks pure functions returning `Decision{allow, reason}`.

### M5 — Backtest Engine
- [ ] Event-driven loop over 1m bars.
- [ ] Cost model applies per-trade (spread + slippage).
- [ ] Realistic fill: entry = requested ± slippage; stops respect gaps.
- [ ] Walk-forward: 12 anchored folds, IS=60%, OOS=40%.
- [ ] Monte Carlo: 500 permutation + 500 block-bootstrap (b=5).
- [ ] Outputs: `trades.parquet`, `equity.parquet`, `metrics.json`, `walkforward.json`, `montecarlo.json`.
- [ ] Deterministic given seed.

### M6 — Validation Gate
- [ ] Reads metrics outputs; evaluates thresholds in §6.2.
- [ ] Writes `data/state/GATE_PASSED` on green with full report; deletes on any red.
- [ ] CLI: `v17 validate --run <run_id>` returns exit code 0/1.

### M7 — MT5 Gateway
- [ ] Single-threaded `MT5Gateway` class with command queue (`queue.Queue`).
- [ ] Methods: `connect`, `disconnect`, `symbol_select`, `tick`, `rates`, `order_send`, `order_modify`, `order_close`, `positions`.
- [ ] Automatic reconnect with backoff.
- [ ] `FakeMT5` with same interface for tests.
- [ ] Contract tests ensure parity on happy path.

### M8 — Live Runner
- [ ] APScheduler cron: start 06:50 London, stop 10:05 London, Mon–Fri.
- [ ] Pre-flight: `GATE_PASSED` present, MT5 connected, calendar fresh, risk engine healthy, no `KILL` sentinel.
- [ ] Tick stream → M3 → M4 → M7 pipeline.
- [ ] State machine: `IDLE → ARMED → IN_TRADE → MANAGED → CLOSED`.
- [ ] Kill switch via file sentinel + Telegram command.
- [ ] Position reconciliation on startup.

### M9 — Observability
- [ ] `structlog` JSONL to `logs/v17-YYYYMMDD.jsonl`, rotating daily.
- [ ] SQLite via SQLAlchemy; migrations via Alembic.
- [ ] Equity curve PNG daily.
- [ ] Daily report markdown.
- [ ] Telegram bot: alerts + commands (`/status`, `/pause`, `/resume`, `/kill`, `/report`).

### M10 — Config + CLI
- [ ] `config.toml` loaded via Pydantic Settings.
- [ ] `.env` for secrets (never committed).
- [ ] CLI via `typer`: `v17 ingest`, `v17 backtest`, `v17 validate`, `v17 paper`, `v17 live`, `v17 report`.
- [ ] `--dry-run` flag on `live` runs full pipeline against FakeMT5.

## 8. Project Structure

```
v_17/
├── pyproject.toml
├── config.toml
├── .env.example
├── .gitignore
├── README.md
├── SPEC.md -> docs/SPEC.md
├── docs/
│   ├── SPEC.md
│   ├── research/
│   ├── decisions/        # ADRs
│   └── superpowers/
│       └── specs/        # per-module sub-specs
├── src/v17/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── data/             # M1
│   ├── structure/        # M2
│   ├── setups/           # M3
│   ├── risk/             # M4
│   ├── backtest/         # M5
│   ├── validation/       # M6
│   ├── mt5/              # M7 (gateway + FakeMT5)
│   ├── live/             # M8
│   ├── obs/              # M9
│   └── common/           # shared types, time, math
├── tests/
│   ├── unit/
│   ├── property/
│   ├── integration/
│   └── fixtures/
├── scripts/              # one-off scripts
├── data/                 # gitignored
│   ├── raw/              # symlinks or copies of Dukascopy CSVs
│   ├── parquet/
│   ├── calendar/
│   └── state/            # GATE_PASSED, KILL sentinels
├── logs/                 # gitignored
└── runs/                 # backtest run artifacts, gitignored
```

## 9. Code Style

- Python 3.11+, type-hinted everywhere (`from __future__ import annotations`).
- `ruff` + `black` + `mypy --strict` on `src/v17/`.
- Pure functions by default; side effects isolated to M7, M8, M9.
- `pydantic` for all config + domain DTOs (`Signal`, `Decision`, `Trade`, `Fill`).
- No `datetime.now()` outside `v17.common.clock` — pass clock as dep for testability.
- No hardcoded paths outside `v17.config`.
- Logger via `structlog.get_logger(__name__)`.
- Docstrings only where the WHY is non-obvious; no comment rot.

## 10. Testing Strategy

- `pytest` + `hypothesis` (property-based for detectors) + `pytest-benchmark` (perf).
- Fixtures: hand-crafted OHLC fixtures reproducing canonical ICT examples from `SrsBlack/ict-knowledge-library`.
- Golden-run regression: lock backtest P&L for a fixed seed + fixed CSV snapshot; CI fails on drift > 0.01%.
- `FakeMT5` for M7/M8.
- Replay harness: feed 1m bars from Parquet into live pipeline at 100× speed; assert same signals as backtest.
- Coverage ≥ 85% on M1–M6.

## 11. Commands (CLI contract)

```
v17 ingest                   # CSV -> Parquet
v17 ingest-calendar          # FF JSON -> cache
v17 backtest --symbol EURUSD --from 2015-01-01 --to 2026-10-18 --seed 42
v17 walkforward --symbol EURUSD --folds 12
v17 montecarlo --run <id> --runs 1000
v17 validate --run <id>      # exits 0 (pass) / 1 (fail)
v17 paper                    # FakeMT5 live loop
v17 live                     # requires GATE_PASSED
v17 report --day today
v17 kill                     # writes KILL sentinel
```

## 12. Dependencies (pinned ranges, locked at build time)

- `python>=3.11,<3.13`
- `MetaTrader5>=5.0.45`
- `smartmoneyconcepts>=0.0.26`
- `pandas>=2.2`, `numpy>=1.26`, `pyarrow>=16`
- `pydantic>=2.7`, `pydantic-settings>=2.3`
- `typer>=0.12`
- `apscheduler>=3.10`
- `sqlalchemy>=2.0`, `alembic>=1.13`
- `structlog>=24.1`
- `python-telegram-bot>=21`
- `httpx>=0.27`
- Dev: `pytest`, `hypothesis`, `pytest-benchmark`, `ruff`, `black`, `mypy`

## 13. Open Questions (none blocking)

None at this time. All design choices locked. Any future ambiguity → ADR.

## 14. Approval

- [ ] User approves this SPEC → unlocks Phase 3 (Architecture + per-module sub-specs).
- Changes to this SPEC post-approval require ADR + user approval.

---

**Spec self-review (completed inline):**
- Placeholders: none.
- Internal consistency: capability map, build order, dependencies cross-checked.
- Scope: focused on one deliverable (ICT bot for FTMO Challenge). Decomposed into M1–M10, each will get a sub-spec in Phase 3.
- Ambiguity: ICT concepts given single formal definitions (§5). FTMO rule constants fixed (§6.3). Validation thresholds fixed (§6.2).
