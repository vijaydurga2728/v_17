# Cycle 23 — Automated Visual Validation of the Frozen Cycle 21 Model A

**Status:** spec v1.0, 2026-11-19. Decisions from the grilling session (rounds 1-2), all approved by the user.
**Baseline:** Cycle 21 engine `src/v17/smc_sb/` frozen at commit `0f7054c` (config `21.2.0`). Not modified by cycle 23.
**Branch:** `cycle23-visual`. **Outputs:** `out/c23/`. **Code:** `src/v17/c23_visual/`.
**Real-data execution: NOT authorized by this spec.** Phases 1-2 are synthetic-only.

## 1. Goal (D1)

An honest pass/fail verdict on Cycle 21 Model A, with the mechanical ICT rules made visible and independently checked.
The visual layer cannot make the strategy profitable and is not allowed to try. If Model A fails its frozen gates, the
outcome is SHELVE and ICT is closed permanently (no cycle 24 ICT variant).

## 2. Scope decisions

| ID | Decision |
|---|---|
| D1 | Goal is an honest verdict, not profitability. |
| D2 | Reopens Cycle 21 Model A only (spec v1.4, NAS100 / SPX / US30, dev 2018-2024). Holdout 2012-2014 stays sealed. No other ICT variant. |
| D3 | Fully automated. No human labelling gate. Charts are audit artifacts the user may inspect optionally. |
| D4 | Rendering: matplotlib static PNG (already a dependency). No new packages. |
| D5 | Baseline committed and frozen before any visual code (`0f7054c`, 72 c21 tests passing). |
| D6 | Engine stays at `src/v17/smc_sb/`; cycle 23 is a separate read-only package `src/v17/c23_visual/`. |
| D7 | Phase 1 then Phase 2 on synthetic data only, then STOP for explicit user approval before any 2018-2024 run. |
| D8 | Second engine = existing independent `scripts/c21_reference_impl.py`, extended to emit candidate/rejection events. Instead of invented 0-100 quality scores, frozen descriptive metrics (§6), report-only, never filters. |
| D9 | Ledger row for every trading day; charts only for candidates that reached the sweep stage or later. |
| D10 | Order Block experiment is out of cycle 23. Revisit only after the baseline verdict, and only if Model A passes. |
| D11 | Pass gate unchanged from c21 R26 (§8). Visual findings may never relax it or add rescue filters. |

## 3. Data flow

```
M1 bid/ask parquet (immutable)
  -> frozen c21 Engine (unchanged)            -> DayResult.events (existing per-stage log)
  -> c23 event_export (read-only adapter)     -> VisualEvent ledger (one row per event, deterministic IDs)
  -> c23 chart_builder                        -> decision-time + outcome PNGs, 4 timeframes
  -> c23 chart_manifest                       -> provenance: event IDs, source bars, fingerprints, PNG hashes
  -> c23 validation                           -> lookahead / coverage / reproducibility checks
  -> (Phase 2) reference-impl events + metrics -> automated disagreement report
```

The visual package never writes strategy parameters, alters trades, or modifies market data.

## 4. Event ledger (Phase 1)

Each engine event becomes a strict, frozen `VisualEvent`:
`event_id, instrument, trading_date, seq, stage, event_time, available_at, timeframe, price, rule_id,
confirmation_status, rejection_reason, payload, data_fingerprint, config_fingerprint, engine_version`.

- `event_id = "{instrument}_{date}_{seq:03d}_{stage}"` — deterministic, unique.
- `available_at` = the moment the engine could legitimately know the event:
  - sweep: close of its 5m candle (`start + 5m`);
  - MSS: close of the 15m confirmation candle; broken swing confirmed at swing-candle start + (right + 1) x 15m;
  - FVG / order: close of FVG candle 3;
  - fill / exit: close of the M1 bar;
  - bias / levels: the day's window start (computed from completed prior data);
  - rejection: the latest `available_at` of the events before it, or the window start.
- Candidate category per day: `filled`, `unfilled_expired`, `rejected_pre_sweep`, `rejected_after_sweep`
  (no MSS / no FVG / PD / target / OTE / setup-after-expiry), `excluded` (non-XNYS, early close, bad quotes, missing M1).
- **Near-miss** (frozen definition): a candidate that produced a sweep and MSS and failed exactly one later stage;
  `near_miss_stage` records which one. No subjective category after seeing outcomes.

## 5. Charts (Phase 1)

Per charted candidate, one PNG per view, each with four panels: D1 context, 15m liquidity/MSS, 5m FVG/entry,
M1 execution.

- **Decision view:** candles and annotations with `available_at <= cut` only. `cut` = order creation time for orders,
  or the rejection's `available_at` for rejected candidates. No fill, exit, P&L or later candles.
- **Outcome view:** same panels extended to exit (or 16:00 for non-filled candidates) with fill/exit annotations.
- Chart ID: `{instrument}_{date}_c23_{decision|outcome}.png`. No random UUIDs.
- Pattern annotations use mid prices; execution annotations use bid/ask, as in the engine.
- Generation is resumable: a chart whose manifest entry and PNG hash already match is skipped; failures are recorded
  in the manifest, never silently skipped.

## 6. Descriptive metrics (Phase 2, report-only)

Frozen before any real data: displacement body/range, displacement range / ATR(14) on 5m, sweep depth (points beyond
reference), sweep close-back-inside (bool), FVG size / ATR(14) on 5m. Reported by winner/loser and agreement status.
Never used to filter trades in cycle 23.

## 7. Gates (must pass in order; Phase 1 = 1-5, Phase 2 = 6)

1. **Baseline isolation:** c21 config fingerprint unchanged; all c21 tests pass; exporting the ledger leaves
   `Engine.run` output identical.
2. **Ledger correctness:** unique deterministic IDs; every rejection has a reason; every event maps to source bars.
3. **No lookahead:** decision view contains no annotation with `available_at > cut` and no candle ending after `cut`;
   FVG not before candle 3 closes; MSS swing confirmed before the MSS; DST covered by the fixtures.
4. **Synthetic fixtures:** exact annotation coordinates and timestamps asserted on hand-computed fixtures
   (`scripts/c21_fixtures.py` + base day), not just "a PNG exists".
5. **Rendering + reproducibility:** every expected chart renders; repeat runs give identical annotation hashes;
   manifest matches files; failures reported.
6. **Independent event parity:** reference implementation and engine produce identical candidate events (time, price,
   stage, rejection reason) on all synthetic fixtures; existing six-seed parity intact.

## 8. Real-data sequence (after explicit user approval only)

1. Real-data parity, 2018-2024, both engines; exact candidate and trade parity required.
2. Generate the full chart set and ledger for NAS100, SPX, US30.
3. Automated disagreement + metric report.
4. Baseline performance run, Model A, SMT disabled, per instrument. Pass requires ALL of: net PF >= 1.30, >= 100
   trades, mean net R > 0, matched-control p <= 0.05/3 = 0.0166667, doubled-cost PF >= 1.10. Report max DD, R^2,
   annual results.
5. No instrument passes -> SHELVE, ICT closed. Any rule defect found visually -> documented; a fix is a new strategy
   version with fresh tests and parity, never a silent change.

## 9. Limitation (stated up front)

Both engines read the same OHLC numbers and were written by the same author. Agreement shows that the code matches the
written rules. It does not show that the written rules match a discretionary ICT trader's judgement.
