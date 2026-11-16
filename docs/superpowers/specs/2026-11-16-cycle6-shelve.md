# Cycle 6 SPX-led FX — SHELVE verdict

**Date:** 2026-11-16
**Branch:** `cycle6-spx-led-fx` HEAD `caa2917`
**Candidate role in ensemble plan:** #2' (SPX-led FX M5 momentum).

## Result

Dev grid (48 configs, AUDUSD + USDJPY M5, 2015-01-01 → 2023-12-31) finished exit=0 at 2026-11-16T14:50:38 after 2h 56m 40s wall. Full output: `out/c6/dev_grid.csv`.

| metric | best config | best value |
|---|---|---|
| PF | K=0.5, slope_window=12, C=0.5 | 0.7678 |
| sharpe | K=0.5, slope_window=12, C=0.5 | -1.3675 |

Top 10 PF range **0.747-0.768**. All 48 configs have PF < 1.0 and sharpe < 0. No profitable region in the grid.

## Pre-reg deviations relative to Task 18 plan

- Calendar input used `data/calendar/*.json` (2021-2024 + 2026-W44 only). Pre-2021 dev years (2015-2020) ran without high-impact-event blackout. User acknowledged at session start (option 1a, memory `project_cycle6_task18_state.md`).

## Decision

**SHELVED.** No edge to carry into scheme-1 MCPT / paired-alpha / holdout. Running further statistical layers on PF < 1.0 is p-hacking.

## Infra retained

- `v17 c6 grid` CLI and underlying pipeline are reusable for any (SPX-leader, FX-follower) hypothesis.
- M5 bars for AUDUSD/USDJPY/USA500IDXUSD built and cached — reusable.
- Calendar cache `data/calendar_cache/ff_c6_index.parquet` reusable.

## Next

Advance to ensemble candidate #3 (overnight gap continuation, SPX D1). Separate branch, separate pre-reg.
