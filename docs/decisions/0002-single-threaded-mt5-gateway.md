# ADR-0002: Single-Threaded MT5 Gateway with Command Queue

## Status
Accepted

## Date
2026-10-28

## Context
The `MetaTrader5` Python package is the live-execution bridge for v17 (ADR implied by SPEC §6 and research `last30days.md`). Independent reports and PRs (e.g., `mohmdstag7-cmd/Tr` PR #11) have verified that the package is **not thread-safe**: concurrent calls from different threads produce silent state corruption, dropped ticks, missed order responses, and process crashes.

The live runner (M8) must concurrently:
- Pull ticks and rates from MT5.
- Submit, modify, and close orders.
- Reconcile positions on startup and after errors.
- Serve status queries from the Telegram bot.
- Log to disk and alert in parallel.

If any of those paths touches `MetaTrader5` from more than one thread, we lose live trades.

## Decision
Isolate every call into the `MetaTrader5` package behind a single-threaded worker:

- One dedicated `threading.Thread` owns the MT5 session.
- Callers push typed command DTOs onto a `queue.Queue`.
- The worker pops commands, executes them synchronously against `MetaTrader5`, and replies via per-command `concurrent.futures.Future` or response queue.
- The `TradeGateway` Protocol (see `docs/API.md`) hides this entirely; callers call `gateway.submit(req)` and get an `OrderResult` back.
- A sibling `FakeMT5` implements the same Protocol for tests and `v17 paper`.

Reconnect, timeout, and backoff logic live in the worker loop.

## Alternatives Considered

### Multi-thread with a `threading.Lock` around each MT5 call
- **Pros**: Minimal change; keeps call sites synchronous.
- **Cons**: The package's non-thread-safety is not limited to critical sections; it includes internal global state that can corrupt even with external locking. "Mostly works" is not acceptable for a trading account.
- **Rejected**: unverifiable safety.

### `asyncio` wrapper around `MetaTrader5`
- **Pros**: Modern Python concurrency; good composition with other I/O.
- **Cons**: The underlying package is synchronous and blocking; wrapping it in `asyncio.to_thread` reintroduces multi-thread access unless the wrapper also serializes to one worker (which is exactly our chosen design, with extra ceremony).
- **Rejected**: no net benefit, more moving parts.

### Separate subprocess owning the MT5 session, IPC over local socket
- **Pros**: Hard isolation; survives in-process crashes of the main runner.
- **Cons**: Adds a second process, IPC serialization, lifecycle management, and a new failure mode (child dies while parent lives). Overkill for a single-user workstation.
- **Rejected**: cost outweighs benefit at MVP scale. Revisit if the runner needs OS-level isolation.

### No gateway abstraction, call `MetaTrader5` directly from one monolithic loop
- **Pros**: Simplest code.
- **Cons**: No test seam; `FakeMT5` would not slot in; same-process alerts/status callers would block the trade loop.
- **Rejected**: breaks testability (SPEC §6.7, `docs/API.md` §5).

## Consequences
- MT5 access becomes deterministic and testable via `FakeMT5`.
- Single worker is a throughput ceiling, but at 1-minute bar cadence and ≤3 trades per day this is irrelevant.
- Any caller that needs an MT5 result blocks on a Future; we must set per-command timeouts (default 5 s submit, 2 s read).
- Reconnect logic lives in exactly one place.
- Any future gateway (e.g., cTrader, MT4) implements the same `TradeGateway` Protocol and can be swapped without touching M8.
