# ADR-0005: Adopt `smartmoneyconcepts` as ICT Primitives Library

## Status
Accepted

## Date
2026-10-28

## Context
Module M2 (Market Structure Engine) needs correct, maintained detectors for Fair Value Gaps, Order Blocks, BOS/CHoCH, swing highs/lows, liquidity pools (BSL/SSL), and session windows. These primitives are the foundation of the Silver Bullet and Judas Swing setups.

Research (`docs/research/agent-reach.md`) surveyed every public ICT codebase. `joshyattridge/smart-money-concepts` (available as `pip install smartmoneyconcepts`) is the only option that is MIT-licensed, maintained in 2026, and whose exposed functions line up with the glossary definitions locked in `docs/SPEC.md` §5.

## Decision
Add `smartmoneyconcepts>=0.0.26` as a project dependency. Wrap it inside `src/v17/structure/` behind our own `StructureEngine` Protocol (see `docs/API.md` §5 M2). Never let the library leak outside M2.

Exact functions consumed:

- `smc.fvg` → FVG zone detection.
- `smc.swing_highs_lows` → window-10 swings.
- `smc.bos_choch` → BOS and CHoCH signals.
- `smc.ob` → Order Block zones.
- `smc.liquidity` → BSL / SSL pools.
- `smc.sessions` → session window masks (overridden by our own London killzone definition).

Any divergence between the library's definition and our glossary is reconciled in favour of the glossary; the wrapper enforces our rules.

## Alternatives Considered

### Hand-roll every detector in `src/v17/structure/`
- **Pros**: Zero third-party risk; exact semantic control.
- **Cons**: Adds weeks of development and testing before any strategy runs; each detector has well-known edge cases we would rediscover painfully; no community verification.
- **Rejected**: slow and bug-prone compared to wrapping a working library.

### Fork `fallenpheonix23/ict-trading-bot` detector code
- **Pros**: Already battle-tested in a live-ish bot context; carries the ATR displacement parameter set we care about.
- **Cons**: Less-maintained upstream; unclear license; style of code is harder to test; still requires significant wrapping.
- **Rejected**: `smartmoneyconcepts` is cleaner, properly licensed, and maintained; we can borrow ATR displacement constants from `fallenpheonix23` separately as risk/structure parameters without taking the detector code.

### Port TradingView Pine Script ICT indicators to Python
- **Pros**: Direct lineage to the most popular public ICT visualizations.
- **Cons**: Manual translation; Pine quirks (series indexing, repainting bars) introduce silent bugs; weeks of work.
- **Rejected**: no durable benefit over the Python library.

### Nautilus Trader's built-in indicators
- **Pros**: Production-grade.
- **Cons**: Nautilus is rejected in ADR-0001 and does not ship ICT-specific detectors anyway.
- **Rejected**: wrong dependency entirely.

## Consequences
- Pin `smartmoneyconcepts>=0.0.26,<0.1`. Lock exact version in `pyproject.toml` and track upstream changes before upgrading.
- M2 wrapper owns the mapping from library output to our DTOs (`Zone`, `Swing`, `Sweep`, `StructureSnapshot`); callers see only our DTOs.
- Property-based tests feed hand-crafted fixtures to the wrapper and assert glossary-compliant output. If the library ever drifts, the wrapper's tests catch it.
- License (MIT) is compatible with any eventual distribution choice.
- If the library stalls or diverges, we can fork or re-implement behind the same `StructureEngine` interface without touching the rest of the system.
