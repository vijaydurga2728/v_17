# Plans Index — v17

Spec: `docs/SPEC.md`
Architecture: `docs/ARCHITECTURE.md`
API: `docs/API.md`
ADRs: `docs/decisions/`

**No git. Local-only project. No worktree, no commits.**

Build order (one plan per module, each independently testable):

| # | Module | Plan file | Status |
|---|---|---|---|
| 1 | M1 Data | `2026-10-28-m1-data.md` | **done** |
| 2 | M2 Market Structure | `2026-10-28-m2-structure.md` | **done** |
| 3 | M3 Setup Engines | `2026-10-28-m3-setups.md` | **done** |
| 4 | M4 Risk Engine | `2026-10-28-m4-risk.md` | **done** |
| 5 | M5 Backtest | `2026-10-28-m5-backtest.md` | **done** |
| 5a | M5a Backtest Perf | `2026-10-28-m5a-perf.md` | **done** |
| 6 | M6 Validation Gate | `2026-10-28-m6-validation.md` | **done** |
| 7 | M7 MT5 Gateway | `2026-10-28-m7-mt5.md` | **done** |
| 8 | M8 Live Runner | `2026-10-28-m8-live.md` | **done** |
| 9 | M9 Observability | `2026-10-28-m9-obs.md` | **done** |
| 10 | M10 Config + CLI | `2026-10-29-m10-cli.md` | **done** |
| 11 | M11 Setup Firing Fix | `2026-10-29-m11-setup-firing-fix.md` | **partial** (code shipped; trades=0 still) |

Rule: next plan is written only after prior module is implemented, tested, and reviewed. No batch-planning the whole system — plans drift from reality fast.
