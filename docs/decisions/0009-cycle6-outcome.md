# ADR 0009 — Cycle 6 outcome (TEMPLATE, awaiting real-data run)

**Date:** <YYYY-MM-DD>
**Status:** PENDING — fill in after Tasks 18 (dev run) and 19 (holdout run) execute on real data.
**Spec:** `docs/superpowers/specs/2026-11-12-cycle6-spx-led-fx-design.md`
**Plan:** `docs/superpowers/plans/2026-11-12-cycle6-spx-led-fx.md`
**Outcome:** `[ PASS | SHELVE | RESCUED-PASS | RESCUED-SHELVE ]`

## Context

Cycle 6 implements an intraday SPX-led risk-on/off FX strategy on AUDUSD and USDJPY. Code is complete and unit/integration tested (527+ passing suite as of commit `7dce310`). Real-data validation (dev grid, MCPT, paired-alpha, holdout) runs from the terminal via:

```
v17 c6 ingest-m1 ...
v17 c6 build-m5 ...
v17 c6 build-calendar ...
v17 c6 grid --spx-root data/bars_m5 --fx-root data/bars_m5 --calendar data/calendar_cache/ff_c6_index.parquet --dev-start 2015-01-01 --dev-end 2023-12-31 --out-csv out/c6/dev_grid.csv
v17 c6 mcpt-dev ... --out-json out/c6/dev_mcpt.json
v17 c6 paired-alpha-dev ... --out-json out/c6/dev_paired.json
v17 c6 dev-report --grid-csv out/c6/dev_grid.csv --trade-log out/c6/dev_trade_log.csv --mcpt-json out/c6/dev_mcpt.json --paired-json out/c6/dev_paired.json --out-md docs/superpowers/plans/c6_dev_gate_report_<YYYY-MM-DD>.md
v17 c6 backtest ... --start 2024-01-01 --end 2026-10-14 --out-trades out/c6/holdout_trade_log.csv --out-equity out/c6/holdout_equity.csv
v17 c6 mcpt-holdout ... --out-json out/c6/holdout_mcpt.json
v17 c6 holdout-report --dev-sharpe <DEV_SHARPE> --trade-log out/c6/holdout_trade_log.csv --mcpt-json out/c6/holdout_mcpt.json --out-md docs/superpowers/plans/c6_holdout_gate_report_<YYYY-MM-DD>.md
```

## Dev summary

Fill from `out/c6/dev_grid.csv` best row + `out/c6/dev_mcpt.json` + `out/c6/dev_paired.json`.

- **Best config:** K=<...>, slope_window=<...>, C=<...>
- **Dev Sharpe:** <...>  | **PF:** <...>  | **Trades:** <...>  | **MCPT p:** <...>
- **Paired alpha:** A1 (vs random) = <...>, A2 (vs regime-only) = <...>, A3 (vs micro-only) = <...>
- **Dev gates:** D1=<pass/fail>, D2=<...>, D3=<...>, D4=<...>, D5=<...>, D6=<...>
- **Ablation gates:** A1=<pass/fail>, A2=<pass/fail>, A3=<pass/fail>
- **Dev all_pass:** <true/false>

## Holdout summary

Fill from `out/c6/holdout_trade_log.csv` + `out/c6/holdout_mcpt.json`.

- **Holdout Sharpe:** <...>  (dev × 0.7 threshold = <...>)
- **Holdout PF:** <...>
- **Holdout MCPT p:** <...>
- **Max daily loss:** <...>
- **Worst month:** <...>
- **Holdout gates:** H1=<pass/fail>, H2=<...>, H3=<...>, H4=<...>, H5=<...>
- **Holdout all_pass:** <true/false>

## Decision

Choose ONE:

- **[ ] PASS** — promote to 30-day paper demo starting <DATE>. Scheduled no earlier than 2026-12-12 (after cycle 4B demo window closes 2026-12-11).
- **[ ] SHELVE** — reason: <failing gate(s)>. No rescue attempted because: <no theory-grounded regime shift identified | rescue preconditions in spec §8.5 not met>.
- **[ ] RESCUE attempted** — regime shift identified on <DATE> (<SPX event>). Extended dev window to <YYYY-MM-DD>. Second holdout run: <PASS|SHELVE>.
  - Rescue dev grid: `out/c6/rescue_dev_grid.csv`
  - Rescue report: `docs/superpowers/plans/c6_rescue_report_<YYYY-MM-DD>.md`

## Consequences

Fill after decision:

- If PASS: Demo starts on <DATE>. Memory updated at `C:\Users\Vijayakumar R\.claude\projects\C--personal-v-17\memory\MEMORY.md` with Cycle 6 pointer and status.
- If SHELVE: Cycle 6 recorded alongside SB, ORB, Gap-Fade, FX cointegration as shelved. Lessons captured in <notes section below>. No further work on this thesis without new evidence.
- If RESCUE-PASS/SHELVE: document which rescue path was used and whether it produced a tradable edge.

## Notes

- What was surprising?
- What should future cycles reuse? (infra on `cycle6-spx-led-fx`: SPX regime module, FX micro-trigger, two-leg position, c6_runner orchestrator, paired-alpha ablation nulls — all cycle-agnostic enough to reuse)
- What would we do differently next time?

## Follow-ups

- [ ] Fill in ALL `<...>` placeholders above.
- [ ] Update `C:\Users\Vijayakumar R\.claude\projects\C--personal-v-17\memory\MEMORY.md` with a `- [Cycle 6 status](project_cycle6_status.md) — <outcome> YYYY-MM-DD.` line and create `project_cycle6_status.md` with a 1-paragraph summary.
- [ ] Commit this ADR alongside the generated dev + holdout gate reports.
