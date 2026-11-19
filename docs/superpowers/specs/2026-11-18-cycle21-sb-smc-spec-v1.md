# Cycle 21 — Silver Bullet SMC Strategy — Technical Specification v1.4 (FROZEN, reviews 1-3 applied)

**Status:** FROZEN 2026-11-18, committed before any cycle 21 code.
**Origin:** user-supplied spec v0.1 (Appendix A, verbatim) + user decisions D1–D16 with binding definitions (Section 1,
verbatim). Python implementation only.
**Execution gate:** NO strategy execution on any market data (development or final exam) until the user/reviewer has
reviewed (a) the implementation, (b) the deterministic tests, (c) the data-integrity audit, (d) the reproducibility
report, and (e) has signed off on each implementation interpretation in Section 3. No parameter optimization. The
final holdout (2012–2014) must not be accessed until that review.

---

## 1. Binding decisions (user, 2026-11-18, verbatim)

> YES — accept D1 through D16 with the following binding implementation definitions.
>
> 1. D1: Daily structure uses strict 2-left/2-right confirmed daily pivots. Bullish requires HH + HL; bearish requires
>    LH + LL. Mixed, equal or insufficient structure means neutral/no trade.
> 2. D2: Sweep detection uses completed 5-minute candles. Asian session is 20:00–00:00 America/New_York, with 00:00
>    exclusive and the range assigned to the following NY trading date. A sweep must trade strictly beyond the reference
>    and close strictly back inside.
> 3. D3: Use strict 2-left/2-right confirmed 15-minute pivots. A pivot is usable only after two subsequent completed
>    candles. MSS requires a completed 15-minute close beyond the latest confirmed opposing swing.
> 4. D4–D6: Use 5-minute FVGs with 15-minute MSS. No additional numerical displacement threshold. The FVG must complete
>    on or after MSS confirmation and be associated with the directional structural shift.
> 5. D7: OTE is the 62–79% retracement zone. Long impulse anchors are the sweep low and highest high reached by MSS
>    confirmation. Short anchors are the sweep high and lowest low reached by MSS confirmation. The FVG proximal edge
>    must lie inside the zone; entry remains at that edge.
> 6. D8: Orders can fill until 11:05 NY, exclusive at the boundary. Cancel unfilled orders at 11:05.
> 7. D9: Stop is exactly at the far FVG boundary, without an additional buffer.
> 8. D10: Existing positions can resolve through stop or target. Force-close any remaining position at 16:00 NY. No new
>    entries after the approved entry window.
> 9. D11: SMT is disabled in the baseline. Later experiment only: NAS100/SPX, SPX/NAS100 and US30/SPX, using
>    synchronized 5-minute data and corresponding session liquidity extremes.
> 10. D12: Maximum one filled trade per instrument per NY trading date. Cancelled/unfilled orders do not consume the
>     limit; a filled and subsequently stopped-out trade does.
> 11. D13: PDH, PDL and NWOG are eligible targets. NWOG is Friday 17:00 NY close to Sunday 18:00 NY open. Use the
>     nearest boundary in the trade direction. A level/zone already traded through or into is ineligible. Select the
>     nearest eligible target providing at least 2R after costs. If none qualifies, no trade.
> 12. D14: Run NAS100, SPX and US30 independently. Never combine their results to hide an individual instrument failure.
> 13. D15: Development data 2018–2024. Untouched historical examination 2012–2014, subject to a data-availability and
>     integrity audit before strategy execution. Label this a backward-time historical generalization test, not a
>     forward-looking test.
> 14. D16: Use actual bid/ask data. Apply 0.5 index points adverse slippage on stops and forced exits, zero index
>     commission only after instrument-specification verification, and report doubled spread/slippage sensitivity.
>     Results are reported in R. The 1% equity risk setting applies only to the FTMO-style drawdown simulation.
>
> Additional restrictions: Freeze these decisions in a versioned specification before coding. Python implementation
> only. No lookahead, no silent missing-data substitution, and no parameter optimization on the final holdout. Keep
> baseline FVG-only and experimental FVG+OTE as separate variants. SMT remains disabled in the baseline. No live
> deployment based on backtest results alone. Before strategy execution, deliver the completed implementation,
> deterministic tests, data-integrity audit and reproducibility report for review. Do not start parameter optimization
> or access the final holdout until implementation and data integrity have been reviewed.

## 2. Instruments and data

| Spec name | Data symbol (Dukascopy M1 bid/ask) | Source path |
|---|---|---|
| NAS100 | `USATECHIDXUSD` | `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev` |
| SPX | `USA500IDXUSD` | `data/bars_m1_paired/USA500IDXUSD` |
| US30 | `USA30IDXUSD` | `data/bars_m1_paired/USA30IDXUSD` |

- Development trading dates: 2018-01-01 → 2024-12-31. Context-only warm-up M1 data from 2017-11-01 (levels and
  pivots only; no trades dated before 2018-01-02).
- Final exam: trading dates 2012–2014 (backward-time historical generalization test). M1 bid/ask data is **not on
  disk** as of freezing; the user must download it. The loader refuses any date before 2017-11-01 or after 2024-12-31
  unless `final_exam=True` is passed explicitly (and that flag is reserved for the post-review exam).

## 1b. Review 1 decisions (user/reviewer, 2026-11-18, verbatim)

> Cycle 21 review decisions:
>
> The current implementation is NOT authorized for strategy execution yet.
>
> APPROVED: R1, R2, R3, R4, R6, R7, R8, R10, R11, R13, R14, R16, R20, R21, R23 and R30, subject to the clarifications in
> this review.
>
> REQUIRED CORRECTIONS:
>
> 1. R5: Require an unswept liquidity reference between its creation and the qualifying sweep. Do not count a level
>    already consumed before the qualifying sweep.
> 2. R9: If no confirmed opposing 15-minute swing exists on the first post-sweep candle, continue scanning. Reject only
>    if no valid MSS appears by 11:00 NY.
> 3. R12: Entry is at the FVG proximal boundary, never candle-3 close. Allow a subsequent distinct valid setup if the
>    previous pending order expires or is cancelled. Maintain one pending order at a time and one filled trade per
>    instrument/day.
> 4. R15: Gap-through stop fills must use the first available bid/ask open plus adverse 0.5-point slippage. Long: bid
>    open - 0.5. Short: ask open + 0.5. Do not fill a gap-through stop at the original stop price. Preserve stop
>    checking on the fill bar and target checking from the following bar.
> 5. R17: Conditional approval. Verify commission against actual MT5 symbol specifications before execution.
> 6. R18: PDH/PDL level creation time is 17:00 NY, consistent with the daily rollover.
> 7. R19: NWOG is Friday 17:00 NY close to Sunday 18:00 NY open.
> 8. R22: Zero commission remains conditional on actual broker symbol-specification verification.
> 9. R24: Revise the random-entry null. The current market-entry control does not fully match the real limit-entry
>    mechanism or entry-time distribution. Specify the randomization, entry timing, execution mechanics, resampling,
>    seed, one-sided plus-one p-value calculation and multiple-testing correction before approval. Do not call it fully
>    matched until those differences are addressed.
>
> R26 — Proposed development pass criteria, separately per instrument: Net PF >= 1.30. At least 100 completed trades.
> Mean net R > 0. Matched-control p-value <= 0.0166667. Doubled-cost PF >= 1.10. Report maximum drawdown, R² and
> annual performance; annual positivity is not a gate.
>
> R27 — Reject every US30 17:00–17:00 session containing crossed quotes. Map every bad timestamp to its exact session
> and exclude contaminated sessions from trades, PDH/PDL and daily pivots. Do not rely on unverified hardcoded
> exclusion dates.
>
> R28 — No entries on XNYS early-close days. Valid early-close daily candles may remain available for subsequent daily
> context. Do not invent a 16:00 exit price.
>
> R29 — Skip non-XNYS CFD sessions for baseline daily candles, daily pivots, PDH/PDL and trading. Use the previous
> completed XNYS session.
>
> R30 — Retain repeated provider-filled bars, flag and report them, and add regression tests against false signal
> creation.
>
> Do not access the 2012–2014 holdout. Do not run the strategy on 2018–2024 yet. After corrections, provide the actual
> source files, tests, updated specification, full audit JSON and reproducibility report for independent review. Then
> complete the independent second implementation and hand-check. Only after those steps will the development baseline
> run be considered for authorization.

## 2b. Decision round 2 (user, 2026-11-18, verbatim: "yes to all")

Questions answered "yes": (1) R31 frozen-quote-side exclusion with a 30-bar run; (2) R5a contamination rejection;
(3) R19 NWOG absent when the Friday or Sunday bar is missing; (4) 0.05/3 per instrument is enough (no family-wise
correction across variants); (5) the user will verify index commission in the FTMO MT5 platform; R17/R22 stay
CONDITIONAL until the value is reported. This answer does not by itself authorize a real-data run (review 1: the
development baseline run is "considered for authorization" only after the review package).

## 2c. Review round 3 (user/reviewer, 2026-11-18; key decisions verbatim)

> **Decision:** Accept zero commission as the documented FTMO index-CFD assumption, but retain the MT5 symbol
> specification as the final account-level verification. Also, zero commission does not mean zero trading costs: the
> Dukascopy bid/ask spread and your slippage assumptions still apply. Do not describe Dukascopy execution costs as an
> exact reproduction of FTMO spreads.
>
> I authorize the two proposed stages, in this order, **after the additional synthetic coverage in section 3
> passes**: 1. Real-data implementation parity — 2018–2024 [...] Require exact trade-by-trade agreement. Any mismatch
> stops the process. [...] 2. Baseline performance run — 2018–2024: Model A only; SMT disabled. Run NAS100, SPX and
> US30 independently. Apply the agreed pass criteria separately to each instrument. Report failures honestly. Do not
> tune parameters or modify rules after seeing results. Preserve the 2012–2014 holdout untouched. This authorizes
> those research runs only. It does **not** authorize optimization, holdout access, parameter changes, or live/demo
> deployment.
>
> Required synthetic cases: gap-through long stop; gap-through short stop; missing 15:59 bar (no invented exit
> price; early-close dates cannot create new entries); OTE Model B valid and invalid with exact entry-zone
> boundaries; OTE + FVG interaction; multiple pending setups (one pending order at a time; cancellation permits a
> later distinct valid setup); fill-bar ambiguity (stop on fill bar; target from the following bar).
>
> Execution sequence: 1. synthetic fixtures, both engines; 2. freeze code, tests, data manifest and configuration
> fingerprint; 3. real-data parity 2018–2024; 4. only after exact parity, the three independent baseline runs;
> 5. keep the 2012–2014 holdout sealed.

Status of R17/R22 after round 3: zero commission **accepted as the documented FTMO assumption**; the MT5 symbol
specification remains the final account-level verification (not yet performed). Costs modelled = Dukascopy bid/ask
spread + 0.5-point stop/forced-exit slippage; these are not FTMO's exact spreads.

**R12a (new, found while building the round-3 fixtures):** with the fixed 11:05 expiry (D8) and no invalidation rule
(R14), an order can only be cancelled by expiry, so a later distinct setup can never become a live order. A setup
whose FVG forms at or after the order expiry is rejected (`setup_after_expiry`), and the re-scan starts at
max(cancellation time, previous order's placement time). Unreachable with the approved 11:05 expiry (FVGs complete by
11:00); it removes a latent infinite loop and is covered by the `one_pending_then_rescan` fixture.

Missing 15:59 bar (R20/R28 as implemented): a position still open exits on the last **real** M1 bar before 16:00
(bid/ask close ∓ 0.5) and is flagged `data_gap`; no 16:00 price is created. On XNYS early-close dates no entry is
allowed at all.

## 3. Implementation rules (status after review 1)

Status: **APPROVED** (review 1), **CORRECTED** (rewritten per review 1; needs re-review), **CONDITIONAL**, or
**NEW** (detail added while implementing a correction; needs review). Config `CONFIG_VERSION = "21.2.0"`.

| # | Status | Rule as implemented |
|---|---|---|
| R1 | APPROVED | Daily candle = NY 17:00 → 17:00 session; trading date = NY date on which the session closes. |
| R2 | APPROVED | Mid price for all patterns/levels; bid/ask only for fills and exits. |
| R3 | APPROVED | 5 m / 15 m candles aligned to the NY wall clock, built from M1; complete only after their end time. |
| R4 | APPROVED | Sweep candle, MSS candle and FVG candle 3 all inside 10:00–11:00 NY. |
| R5 | CORRECTED | Long refs PDL, Asian low; short refs PDH, Asian high. Creation: PDH/PDL at 17:00 NY on the date of the session they come from (R18); Asian high/low at 00:00 NY of the trading date (range complete). A ref is **consumed** at its first M1 mid price strictly beyond it after creation. The qualifying sweep is the 5 m candle containing that first breach, only if that candle lies inside the window and closes strictly back inside; otherwise the ref is consumed and cannot qualify that day. Earliest qualifying candle across refs wins (tie: PD before ASIA). |
| R5a | APPROVED (round 2) | If any part of a ref's [creation, sweep candle start) window, or a target's touch window, lies in an excluded session (R27), the day is rejected (`reference_window_contaminated`): consumption/touch cannot be verified without those bars. |
| R6 | APPROVED | No Asian bars → Asian ref absent (logged). |
| R7 | APPROVED | Strict 2/2 daily pivots on completed sessions before the trading date (daily table per R29/R27); HH+HL bullish, LH+LL bearish, else neutral. |
| R8 | APPROVED | Equilibrium of latest confirmed daily pivot high and low; entry limit price strictly below (long) / above (short). |
| R9 | CORRECTED | Scan completed 15 m candles in the window closing after the sweep candle close; for each, reference = latest 15 m 2/2 pivot whose right-side candles completed before it started. Candles with no confirmed swing are skipped (scanning continues). MSS = first candle closing strictly beyond its reference. Rejected (`no_mss`) only if none by 11:00. |
| R10 | APPROVED | Continuous 15 m candles (all sessions) for pivots. |
| R11 | APPROVED | First directional 5 m FVG with candle 3 closing in [MSS close, 11:00], three contiguous candles, no size minimum. |
| R12 | CORRECTED | Limit **price** = FVG proximal boundary (top for longs, bottom for shorts), never a candle close. The order is **placed** at candle-3 close (the first moment the FVG exists). One pending order at a time. If it expires/cancels unfilled, scanning restarts for a distinct setup whose sweep candle starts at or after the cancellation time; R5 consumption makes an already-swept ref ineligible. One filled trade per instrument per day. With expiry 11:05 and the window ending 11:00, no second setup can form in the baseline; the mechanism is implemented and unit-tested with a shorter test expiry. A setup rejected before an order exists ends the day (no order was pending). |
| R13 | APPROVED | M1 fills from placement to 11:05 (exclusive); long ask_low ≤ limit, short bid_high ≥ limit; fill at the limit. |
| R14 | APPROVED | No FVG invalidation beyond expiry. |
| R15 | CORRECTED | Stop checked first on every bar from the fill bar; target from the following bar; both in one bar → stop. Stop exit: long = stop − 0.5 unless that bar's bid open < stop (gap-through), then bid open − 0.5; short = stop + 0.5 unless ask open > stop, then ask open + 0.5. Applies on the fill bar too. Target exit = target exactly. |
| R16 | APPROVED | Force close on the M1 bar ending 16:00: bid close − 0.5 (long) / ask close + 0.5 (short). |
| R17 | CONDITIONAL | 1R = \|entry − stop\| + 0.5 + commission; estimated reward = \|target − entry\| − commission ≥ 2R. Commission to be verified (R22). |
| R18 | CORRECTED | Candidates PDH, PDL, NWOG boundary nearest in the trade direction, strictly beyond entry. PDH/PDL created 17:00 NY on the date of the previous XNYS session (R29). Touched = any mid low ≤ level ≤ any mid high in [creation, placement). NWOG touched = mid trades strictly inside the open gap in [Sunday 18:00, placement). Nearest first; first with ≥ 2R. |
| R19 | APPROVED (round 2) | NWOG = last mid close of a bar starting in [Thursday 17:00, Friday 17:00) and first mid open of a bar starting in [Sunday 18:00, Monday 17:00) NY. **NEW:** if either bar does not exist (e.g. no Friday session), the NWOG is absent (no substitution). Zero width → absent. |
| R20 | APPROVED | Any missing M1 in 09:30–11:05 → day rejected; missing 15:59 bar with an open position → `data_gap` flag. |
| R21 | APPROVED | XNYS calendar, pandas_market_calendars 5.6.1. |
| R22 | CONDITIONAL | Zero commission pending broker symbol-specification verification. Not verifiable from the price data or the MT5 Python symbol API (commission is set per account group); requires the user to read it in the FTMO platform or from a test deal. |
| R23 | APPROVED | Doubled cost: spread ×2 around mid, slippage 1.0. |
| R24 | CORRECTED | See section 3a. |
| R25 | experiment | SMT unchanged, disabled in baseline. |
| R26 | APPROVED | Per instrument: net PF ≥ 1.30, ≥ 100 trades, mean net R > 0, matched-control p ≤ 0.0166667, doubled-cost PF ≥ 1.10; report max DD, R², annual results (not a gate). |
| R27 | CORRECTED | Every M1 bar with ask < bid on any of o/h/l/c is mapped by code to its 17:00–17:00 trading date; all bars of those sessions are removed; those sessions are excluded from trades, PDH/PDL and daily pivots (the next day uses the previous valid XNYS session). No hardcoded dates. |
| R28 | CORRECTED | No entries on XNYS early-close days (calendar market_close earlier than 16:00 NY). Their daily candles stay in the daily table. |
| R29 | CORRECTED | Daily table = XNYS sessions only (minus R27 exclusions). Non-XNYS CFD sessions are excluded from daily candles, pivots, PDH/PDL and trading. Their M1 bars remain for intraday candles, 15 m pivots (R10) and touch/consumption checks (price did trade then). |
| R31 | APPROVED (round 2) | Audit after review 1: the US30 **ask is frozen at 24567.25 from 2020-03-10 20:00 to 2020-03-31 19:59 NY** (20,025 bars, 15 full sessions, spreads up to ~6,400 pts); these bars are not crossed, so R27 misses them and every mid price there is wrong. Proposal: a session is excluded exactly like R27 if it contains a run of ≥ 30 consecutive M1 bars in which one quote side is flat (o=h=l=c) and unchanged from the previous bar while the other side moves. Evidence for 30: the longest such run on 2017-11 → 2024 data is 23 bars (NAS100), 11 (SPX), 9 on US30's bid side; US30's frozen ask runs reach 7,200 bars. Config `stale_min_run=30` (build_market). |
| R30 | APPROVED | M1 bars identical (all 8 bid/ask OHLC) to the previous bar are retained and flagged; each trade records the flagged-bar count between sweep start and fill; the audit reports totals. Regression tests confirm repeated bars cannot create sweeps, pivots or FVGs. |

### 3a. R24 matched control (revised; not "fully matched")

- **Matched per real trade j:** same side, same placement minute after 10:00, same limit offset from the placement
  price, same stop distance and same target distance (points). One control trade per real trade per permutation.
- **Placement price:** ask close (long) / bid close (short) of the last M1 bar before placement. Real offset
  `L_j = (placement price − limit) × side`.
- **Randomization:** a day drawn uniformly with replacement from eligible development days of the same instrument
  (XNYS, not early-close, not excluded, complete 09:30–11:05 M1). Control limit = that day's placement price −
  side × L_j; stop = limit − side × S_j; target = limit + side × T_j.
- **Execution:** identical R13 fill (until 11:05), R15 exits (gap rule), R16 force close, R17 R unit.
- **Resampling:** an unfilled control draws a new day (up to 100 attempts per control trade; exhausting them aborts
  the test with an error). The control fill rate is reported.
- **Statistic:** mean net R of the N control trades; 5,000 permutations.
- **p-value:** one-sided, plus-one: p = (1 + #{null mean ≥ real mean}) / (5,000 + 1).
- **Seed:** `numpy.random.default_rng(2026112100 + 10 × instrument_index + variant_index)`; instrument index NAS100 0,
  SPX 1, US30 2; variant A 0, B 1, SMT 2. Draw order fixed (permutation → trade → attempt; day index then nothing else).
- **Multiple testing:** Bonferroni over the 3 instruments within each variant, α = 0.05 / 3 = 0.0166667 (R26). OTE and
  SMT experiments are extra families; their p-values are also reported against 0.05 / 9. Whether a family-wise
  correction across variants is required: **decided in round 2 — no; Bonferroni 0.05 / 3 within each
  variant is sufficient; 0.05 / 9 reported for reference only.**
- **Remaining differences (why it is not called fully matched):** the control does not condition on the bias / sweep /
  MSS / FVG context (that context is what is tested); distances are in points, not volatility-normalized; the control
  day's directional drift is not matched.

### Changelog (pre-execution; no results exist)

- v1.0 → v1.1: R19 zero-width NWOG absent, strict-inside touch; R24 bid/ask open; R27–R30 added from the audit.
- v1.1 → v1.2 (review 1): approvals recorded; R5, R9, R12, R15, R18, R19, R24, R27, R28, R29 corrected; R26 adopted;
  R5a and the R19 missing-bar rule are new and need review. Config 21.2.0.
- v1.3 → v1.4 (review round 3): commission decision recorded; R12a `setup_after_expiry` guard + re-scan start
  (both engines); targeted synthetic fixtures `scripts/c21_fixtures.py` (13 cases) must pass with exact parity
  before real data. Config unchanged (21.2.0).
- v1.2 → v1.3 (decision round 2): R5a, R19, R31 approved; Bonferroni 0.05/3 per variant confirmed. No code or
  parameter change (config stays 21.2.0). R22 commission still pending user verification.

## 4. Module layout (Python)

`src/v17/smc_sb/`: `config.py`, `data.py` (loading, guards, candles, integrity), `session.py`, `market_bias.py`,
`liquidity.py` (PDH/PDL, Asian, NWOG, targets), `sweep.py`, `structure.py` (pivots, MSS), `fvg.py`,
`premium_discount.py`, `entry_models.py` (Model A, Model B), `execution.py` (fills, exits, costs), `smt.py`,
`engine.py` (per-day pipeline, event log, trade records), `matched_random.py` (§3a matched control).
Every stage returns either an object or a rejection reason; the engine records both.

## 5. Order of work

1. Spec v1.0 committed (done); v1.1 (done); v1.2 after review 1 (this version).
2. Code + deterministic tests (done; review-1 corrections and regression tests added).
3. Data-integrity audit of development data, no strategy execution (done; re-run after R27/R29/R31).
4. Reproducibility report (done; re-run).
5. Independent second implementation (`scripts/c21_reference_impl.py`, no shared strategy code) compared day by
   day and trade by trade against the main engine on deterministic **synthetic** markets with injected faults
   (`scripts/c21_synthetic.py`, `scripts/c21_reference_check.py`), plus a hand-check table. Real-data comparison is
   deferred because it would be strategy execution on 2018–2024.
6. **Stop for review.** Open items: R5a, R19 missing-bar rule, R31 threshold, 3a family-wise correction, R22
   commission verification. Only after authorization: real-data reference match on 2018–2024, then the baseline
   development run.

---

## Appendix A — User specification v0.1 (verbatim)

### Silver Bullet SMC Strategy — Technical Specification

**Version:** 0.1 — Review Draft  
**Strategy:** New York AM Silver Bullet  
**Primary instruments:** NAS100, SPX, US30  
**Primary session:** 10:00–11:00 America/New_York  
**Status:** Not approved for implementation until unresolved decisions are finalized.

---

#### 1. Strategy objective

Develop a rules-based ICT Silver Bullet strategy that identifies liquidity sweeps, confirms directional market structure shifts, identifies displacement and fair value gaps, and executes limit entries at predefined locations.

The objective is to establish a statistically defensible trading edge after realistic transaction costs.

The strategy must not be optimized to achieve a predetermined win rate or historical profit factor.

#### 2. Trading session

### Approved rules

- Primary session: 10:00–11:00 AM New York time.
- Timezone: America/New_York.
- Daylight-saving transitions must be handled automatically.
- No signals outside the approved session.
- The 03:00–04:00 and 14:00–15:00 windows are separate research experiments and must not be combined with the primary strategy results.

### Unresolved

- Exact entry-order expiry after the 11:00 session end.
- Whether an existing open position can remain active after the session ends.
- Whether a session cutoff forces position liquidation or only prevents new entries.

#### 3. Direction and liquidity targets

### Approved rules

Direction must be established using higher-timeframe context.

Eligible primary external liquidity references:

- Previous Day High (PDH).
- Previous Day Low (PDL).
- New Week Opening Gap (NWOG).

Weekly liquidity may be evaluated as a separate optional experiment.

Rolling 20-, 40- and 60-day highs/lows are excluded from the baseline.

A liquidity level's location above or below current price alone must not determine directional bias.

### Target selection

- Long positions target an eligible untouched external liquidity level above entry.
- Short positions target an eligible untouched external liquidity level below entry.
- The selected target must be recorded at signal-generation time.
- The target must provide at least 2R after estimated trading costs.

### Unresolved

- Exact higher-timeframe directional-bias algorithm.
- Exact NWOG calculation, timezone and validity period.
- Definition of an untouched liquidity level.
- Priority when multiple eligible targets are available.
- Whether a target becomes invalid when partially traded through.

#### 4. Liquidity sweep

### Approved rules

A valid setup requires a meaningful liquidity event before the entry model becomes eligible.

The sweep must:
- Occur before the qualifying MSS.
- Be associated with a predefined liquidity reference.
- Be confirmed using completed candles.
- Be recorded with its reference level, timestamp and extreme price.

The strategy must not treat every minor wick as a valid liquidity sweep.

Midnight session lows and previous-hour lows must not automatically be treated as the universal sweep reference.

### Unresolved

The exact eligible sweep-reference set must be selected and formally defined.

Potential references requiring an explicit decision:
- Previous Day High/Low.
- Previous session high/low.
- Asian session high/low.
- Previous-hour high/low.
- Equal highs/equal lows.
- Other explicitly defined external liquidity.

The developer must not combine these references without a separately approved experiment.

#### 5. SMT divergence

### Approved rules

SMT divergence is optional confluence, not a mandatory baseline entry condition.

The implementation must support:
- SMT disabled.
- SMT enabled.

Comparisons must use instruments with a defensible market relationship and synchronized timestamps.

For index comparisons, the mapping must be explicitly configured rather than inferred from symbol names.

Missing SMT must not invalidate an otherwise valid baseline setup.

### Unresolved

- Exact instrument pairings for NAS100, SPX and US30.
- Exact swing-reference algorithm.
- SMT comparison timeframe.
- Maximum permitted timestamp difference.
- Whether divergence is measured against the same session's extremes or confirmed swing points.

SMT-on and SMT-off results must be reported separately.

#### 6. Market Structure Shift (MSS)

### Approved rules

- MSS timeframe: 15-minute.
- Exactly one confirmed MSS is required to qualify the directional shift.
- MSS must occur after the relevant liquidity sweep.
- Only completed 15-minute candles may confirm MSS.
- A long setup requires a bullish structural break.
- A short setup requires a bearish structural break.
- No subjective 1-minute MSS requirement.
- No retrospective use of future candles.

### Unresolved

- Exact short-term swing-high/swing-low detection algorithm.
- Number of left/right confirmation bars for swing detection.
- Whether the structural break requires a candle close beyond the swing or another condition.
- Whether the MSS candle can also create the qualifying FVG.
- Maximum permitted time between sweep and MSS.

These definitions must be frozen before coding.

#### 7. Displacement and Fair Value Gap

### Approved rules

A valid directional displacement and three-candle FVG are required.

Bullish FVG:

- The low of candle 3 is above the high of candle 1.
- FVG zone: candle 1 high to candle 3 low.

Bearish FVG:

- The high of candle 3 is below the low of candle 1.
- FVG zone: candle 3 high to candle 1 low.

The FVG must:
- Be associated with the qualifying structural shift.
- Be formed in the intended direction.
- Remain valid when the entry is evaluated.
- Be recorded with its boundaries and formation timestamp.

Only completed candles may be used to establish the FVG.

### Excluded assumptions

Do not automatically impose:
- 65% minimum candle-body ratio.
- 1.5x average candle-range requirement.

These numerical thresholds are not approved baseline rules.

### Unresolved

- FVG detection timeframe.
- Minimum FVG size, if any.
- Exact objective definition of displacement.
- Whether the FVG must form before, on, or after the MSS confirmation candle.
- FVG invalidation and mitigation rules.

#### 8. Premium and discount

### Approved rules

Use the last confirmed daily swing range.

Calculate equilibrium:

Equilibrium = (Confirmed Daily Swing High + Confirmed Daily Swing Low) / 2

- Long setups are eligible only in discount, below equilibrium.
- Short setups are eligible only in premium, above equilibrium.
- Use only confirmed daily swing points available at the time of the signal.
- Do not replace this range with a rolling 20-day range.
- Weekly range is optional and disabled in the baseline.

### Unresolved

- Exact daily swing-point detection algorithm.
- Minimum bars required to confirm a swing.
- Treatment of equal highs/lows and incomplete daily candles.

#### 9. Entry models

Two entry models must be supported as separate experiments.

### Model A — FVG-only baseline

- Place a limit order at the FVG proximal edge.
- Long: upper boundary of the bullish FVG.
- Short: lower boundary of the bearish FVG.
- The order remains valid only for the approved setup lifetime.
- Cancel the order when expired or invalidated.
- Never extend an expired order to obtain a fill.

### Model B — FVG + OTE

- Require the same valid FVG as Model A.
- Add an OTE retracement condition.
- Do not assume 70.5% is the approved retracement level.
- Define the impulse-leg anchors and retracement calculation before implementation.
- Do not mix results from Models A and B.

The OTE model is a separate validation experiment, not an automatic replacement for the baseline.

### Unresolved

- Exact FVG timeframe.
- Order lifetime in bars.
- OTE percentage or permitted range.
- Exact impulse-leg anchor selection.
- Whether OTE must overlap the FVG or whether the OTE level itself becomes the entry price.
- Limit-order fill behavior when price gaps through the limit.

#### 10. Stop-loss, target and risk management

### Approved rules

Stop-loss:
- Use the far boundary of the qualifying FVG.
- Long: beyond the lower FVG boundary.
- Short: beyond the upper FVG boundary.
- Do not silently substitute the sweep extreme as the stop.

Target:
- Use the predefined eligible opposing external liquidity level.
- Minimum reward-to-risk: 2:1 after estimated costs.
- Reject setups that cannot realistically provide the required reward-to-risk ratio.

Risk:
- Risk per trade: 1% of account equity.
- Position size must be calculated from the actual entry-to-stop distance and instrument contract specifications.
- Include transaction costs in risk and position sizing.

### Unresolved

- Whether an additional stop buffer is required.
- Account currency and instrument contract-value conversion.
- Maximum concurrent positions.
- Maximum daily account risk.
- Handling of partial fills and rejected orders.

#### 11. Exit management

### Approved rules

Exit on:
- Predefined stop-loss.
- Predefined liquidity target.

Unfilled orders must be cancelled on expiry or invalidation.

Do not introduce an arbitrary 60-minute market-close exit.

All execution decisions must use information available at the relevant timestamp.

### Unresolved

- Whether positions can remain open beyond the Silver Bullet session.
- Whether a separate daily liquidation deadline is required.
- Handling of market gaps through stops or targets.
- Handling of broker execution failures and partial fills.

#### 12. Execution and data integrity

Mandatory implementation requirements:

- Use correct broker-specific instrument symbols.
- Use synchronized market data for correlated instruments.
- Use bid/ask-aware execution rather than assuming all trades execute at midpoint.
- Model spread, commission and adverse slippage.
- Define deterministic limit-order fill rules.
- Apply stop/target ordering consistently when both are touched within one bar.
- Prevent lookahead bias.
- Prevent duplicate signal generation.
- Record every rejected setup and its rejection reason.
- Record every order's creation, modification, expiry, fill and cancellation.
- Handle missing candles and market holidays explicitly.
- Do not silently substitute missing market prices.

Each trade record must include:

- Instrument.
- Trading date.
- Session.
- Direction.
- HTF bias.
- Liquidity reference.
- Sweep timestamp and price.
- SMT status.
- MSS timestamp and broken swing.
- Displacement candle.
- FVG boundaries and timeframe.
- Premium/discount state.
- Entry model and limit price.
- Stop and target.
- Risk and reward in R.
- Actual fills and costs.
- Exit reason.
- Net P&L.

#### 13. Research and validation

The baseline must be frozen before parameter experiments.

Required experiment sequence:

1. Baseline: FVG-only, SMT disabled.
2. Separate experiment: FVG + OTE.
3. Separate experiment: SMT enabled.
4. Any displacement-threshold experiment must be preregistered independently.
5. Select the candidate using development and walk-forward evidence.
6. Freeze the selected strategy.
7. Run one genuinely untouched out-of-sample examination.

Do not repeatedly tune against the final holdout.

The final examination must include:
- Realistic spread, commission and slippage.
- Profit factor.
- Expectancy per trade.
- Win rate.
- Maximum drawdown.
- Equity-curve R².
- Trade count.
- Annual breakdown.
- Matched random-entry comparison.
- Statistical significance.
- Sensitivity to doubled transaction costs.

The luck test must compare against matched random-entry strategies with equivalent direction, trade count, exposure, session and holding-period characteristics.

A buy-and-hold comparison alone is insufficient to establish signal superiority.

No live deployment is permitted based solely on historical profitability.

#### 14. Implementation restrictions

The developer must:

- Implement only explicitly approved rules.
- Keep baseline and experimental variants separate.
- Record all parameter values in a versioned configuration.
- Maintain deterministic backtests.
- Include unit tests for every signal-generation stage.
- Include regression tests for session boundaries, DST, missing candles, FVG formation, MSS confirmation, limit fills and stop/target ordering.
- Preserve the original strategy implementation and results.
- Never change parameters after inspecting final holdout results.

**No unresolved decision may be silently replaced by a developer assumption.**
