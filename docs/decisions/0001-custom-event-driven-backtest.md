# ADR-0001: Custom Event-Driven Python Backtester

## Status
Accepted

## Date
2026-10-28

## Context
The v17 trading system needs a backtest engine capable of:

- Processing 1-minute OHLCV bars over 12 years (2014–2026) for EURUSD + GBPUSD.
- Multi-timeframe alignment (Daily / 4H / 15m / 1m) because ICT setups require HTF bias plus LTF entry.
- Tick-level or sub-bar realistic fills (spread, slippage, gap-respecting stops) to match FTMO Standard cost model.
- Walk-forward orchestration (12 anchored folds, IS/OOS 60/40).
- Monte Carlo on completed trade sequences (hybrid permutation + block-bootstrap, see ADR-0004).
- Deterministic given a seed, so the validation gate (M6) can be trusted.
- Fast enough to complete a full 12-year dual-pair run in under 15 minutes on the operator's workstation.

ICT setups are inherently state-dependent (unmitigated zones, liquidity sweeps that occurred earlier, consistency rule accounting), which rules out purely vectorized paradigms.

## Decision
Build a **custom event-driven backtester in pure Python** inside `src/v17/backtest/`, using `pandas` + `numpy` for bar storage and plain Python loops for event sequencing. Keep the Backtester behind a single `Backtester.run(cfg: BacktestConfig) -> RunReport` interface (see `docs/API.md`).

## Alternatives Considered

### Nautilus Trader (nautechsystems/nautilus_trader)
- **Pros**: Rust core, event-driven, production-grade abstractions.
- **Cons**: No MT5 execution adapter; v2 is pre-production; large API surface to learn; LGPL licensing complication; no first-class walk-forward or Monte Carlo tooling.
- **Rejected**: live-execution target is MT5, and no MT5 adapter exists. Adopting Nautilus would force a second gateway stack we cannot test against our actual broker.

### Backtrader (mementum/backtrader)
- **Pros**: Mature API, extensive community strategies, built-in metrics.
- **Cons**: Repository unmaintained since 2023; Python 3.12 compatibility issues; bar-level fills only; multi-TF support exists but is awkward; no walk-forward or MC.
- **Rejected**: unmaintained upstream equals an uncontrolled dependency on a critical system. Betting FTMO capital on dead software is unacceptable.

### backtesting.py (kernc/backtesting.py)
- **Pros**: Clean API, fast, pandas-native, good charts.
- **Cons**: Single-timeframe engine; bar-close fills only; no realistic intra-bar execution model; no walk-forward orchestrator; no MC.
- **Rejected**: ICT needs multi-TF alignment and sub-bar fills. Working around these would mean reimplementing the parts of backtesting.py we need.

### vectorbt / vectorbtpro (polakowo/vectorbt)
- **Pros**: Extremely fast via NumPy vectorization; portfolio-level analytics.
- **Cons**: Vectorized paradigm assumes stateless signal columns; ICT setups depend on event-order state (unmitigated zone tracking, prior-sweep memory, consistency rule accounting); vectorbtpro is paid.
- **Rejected**: wrong paradigm. Forcing state-dependent logic into vector math produces unreadable code and subtle bugs that pass tests but mis-trade live.

### Lumibot (Lumiwealth/lumibot)
- **Pros**: Supports multiple brokers out of the box, strategy abstraction.
- **Cons**: No MT5 broker adapter; focused on US equities / Interactive Brokers / Alpaca; limited multi-TF semantics; walk-forward and MC are external.
- **Rejected**: MT5 is non-negotiable for FTMO; Lumibot would require a hand-rolled MT5 broker, defeating the point of using it.

## Consequences
- We own the backtest engine entirely; no upstream rot, no license surprises.
- Scope is bounded: the engine only has to support what SPEC §4 M5 requires.
- We can enforce determinism and cost-model fidelity to match FTMO Standard exactly.
- Downside: we write more code and own more maintenance than if an off-the-shelf library fit. Mitigated by keeping the interface deep (`Backtester.run`) and the internals plain.
- Future replacement is cheap: the Backtester Protocol is a seam. If Nautilus ships a stable MT5 adapter and strong WF/MC tooling, we can swap behind the same interface.
