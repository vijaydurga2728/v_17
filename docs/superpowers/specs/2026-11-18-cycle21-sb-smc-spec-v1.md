# Cycle 21 — Silver Bullet SMC Strategy — Technical Specification v1.0 (FROZEN)

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

## 3. Implementation interpretations requiring reviewer sign-off (NOT approved rules)

The decisions above leave the following details open. Each is implemented as a named field in the versioned
configuration (`src/v17/smc_sb/config.py`, `CONFIG_VERSION = "21.1.0"`) with the proposed value below. None is
approved until the reviewer signs off; changing any value creates a new config version and must happen before any
strategy execution.

| # | Topic | Proposed interpretation | Config field |
|---|---|---|---|
| R1 | Daily candle | NY 17:00 → 17:00 session (matches broker MT5 D1 and the D13 NWOG "Friday 17:00 close"). Trading date = the NY date on which the session closes at 17:00. PDH/PDL = high/low of the previous completed session. | `daily_rollover_hour=17` |
| R2 | Pattern price | Mid price ((bid+ask)/2) for all candles, levels, pivots, sweeps, MSS, FVG, OTE and equilibrium. Bid/ask only for fills and exits. | `pattern_price="mid"` |
| R3 | Candle alignment | 5 m and 15 m candles aligned to the NY wall clock (:00, :05 … / :00, :15, :30, :45), built from M1 bars. A candle is complete only when its end time has passed. | — |
| R4 | Signal window | Sweep candle, MSS candle and FVG candle 3 must all close within 10:00–11:00 NY (candle start ≥ 10:00, end ≤ 11:00). "No signals outside the approved session." | `window_start="10:00"`, `window_end="11:00"` |
| R5 | Sweep side | Bullish bias → only sell-side references (PDL, Asian low): 5 m low < ref and 5 m close > ref. Bearish → buy-side (PDH, Asian high): high > ref and close < ref. The first such candle in the window is the sweep. No "freshness" condition (a reference already traded through earlier that day is still eligible). | `sweep_refs=("PD","ASIA")` |
| R6 | Missing Asian range | If no M1 bars exist in 20:00–00:00 for the date, the Asian reference is absent (PDH/PDL still usable). Logged. | — |
| R7 | Daily bias | Pivots on completed daily sessions before the trading date only. Pivot high at day k: high[k] > high of each of days k−2, k−1, k+1, k+2 (strict); usable from day k+3. Bullish = latest confirmed pivot high > previous pivot high AND latest pivot low > previous pivot low. Bearish = both lower. Otherwise neutral. | `daily_pivot_left=2`, `daily_pivot_right=2` |
| R8 | Premium/discount range | Latest confirmed daily pivot high and latest confirmed daily pivot low (R7). Equilibrium = midpoint. The **entry limit price** must be strictly below (long) / above (short) equilibrium. | `pd_price="entry"` |
| R9 | MSS reference swing | For each completed 15 m candle whose close is after the sweep candle's close: reference = latest 15 m pivot high (long) / low (short) whose 2 right-side candles completed before this candle started. MSS = first such candle closing strictly beyond the reference. Exactly one MSS: the first. If the first candle checked has no confirmed swing, the setup is rejected. | `mss_pivot_left=2`, `mss_pivot_right=2` |
| R10 | 15 m pivot history | 15 m pivots are found on continuous 15 m candles (all sessions, no reset at midnight). | — |
| R11 | FVG selection | First 5 m FVG in the trade direction whose candle 3 closes at or after the MSS candle close and no later than 11:00. "Associated with the structural shift" = first such FVG after MSS; no other filter. No minimum size. | — |
| R12 | Order placement | Limit placed at FVG candle-3 close. Only one pending order per instrument; the first qualifying setup only (D12 limit + "prevent duplicate signals"). | — |
| R13 | Fill rule | Executed on M1 bid/ask bars starting at the first M1 bar after placement, until 11:05 (exclusive). Long fills when ask_low ≤ limit; short when bid_high ≥ limit. Fill price = limit price even when the bar gaps through (no price improvement). | `fill_resolution="M1"` |
| R14 | FVG invalidation before fill | None beyond expiry (price must pass the proximal edge before the far edge; a gap through both fills, then the stop is evaluated on that bar). | — |
| R15 | Exit ordering | On every M1 bar from the fill bar: stop checked first (long: bid_low ≤ stop; short: ask_high ≥ stop). Target (long: bid_high ≥ target; short: ask_low ≤ target) checked from the bar after the fill bar. Stop and target in one bar → stop. Stop fill = stop ∓ 0.5 pt slippage. Target fill = target exactly. Gap through stop: fill at stop ∓ slippage (not at the gap open). | `slippage_pts=0.5` |
| R16 | Force close | If still open, exit at the M1 bar ending 16:00 NY: bid close (long) / ask close (short) ∓ 0.5 pt slippage. | `force_close="16:00"` |
| R17 | R unit and "2R after costs" | 1R = |entry − stop| + slippage + round-trip commission (per unit). Estimated reward = |target − entry| − commission. Target qualifies if estimated reward ≥ 2 × 1R. Realized R = net P&L per unit / 1R. | `min_rr=2.0`, `commission_pts=0.0` |
| R18 | Target eligibility | Candidates: PDH, PDL, NWOG upper and lower boundary, strictly beyond the entry in the trade direction. "Traded through or into" = any mid price touch of the level from its creation (PDH/PDL: session start 18:00; NWOG: Sunday 18:00) up to the order placement time. Ordered nearest-first; first candidate with ≥ 2R (R17) is the target. | — |
| R19 | NWOG | Lower/upper = min/max of (last mid close at or before Friday 17:00, first mid open at or after Sunday 18:00). Valid from Sunday 18:00 until touched. Zero-width gap → single level. Only the current week's NWOG. | — |
| R20 | Missing data | A trading date is rejected (logged, no substitution) if any M1 bar is missing between 09:30 and 11:05 NY, or if the force-close bar at 16:00 is missing while a position is open (trade flagged `data_gap`). Non-XNYS dates are skipped. | — |
| R21 | Trading calendar | XNYS sessions (pandas_market_calendars 5.6.1), including early-close days. | — |
| R22 | Commission | 0 on indices: FTMO states index CFDs are commission-free (ftmo.com/en/zero-commissions-on-indices). **Still to verify** against the MT5 symbol specification (US100.cash / US500.cash / US30.cash) before execution. | `commission_pts=0.0` |
| R23 | Doubled-cost sensitivity | Spread doubled by widening each M1 bar symmetrically around mid (bid − s/2, ask + s/2, where s = ask − bid), plus slippage doubled to 1.0 pt. | — |
| R24 | Matched random-entry null | For each real trade: random XNYS dev date (same instrument), same direction, entry at the mid open of a random M1 bar in 10:00–11:05, the same stop and target distances (in points) as the real trade, same exits (R15, R16). 5,000 permutations, plus-one p-value on mean R. Seed fixed per instrument. | `null_perms=5000` |
| R25 | SMT (experiment only, disabled) | Partner pairs NAS100→SPX, SPX→NAS100, US30→SPX. Same 5 m timestamps (max difference 0). Long: primary's sweep candle makes a new low below its reference while the partner's low from 10:00 up to that candle stays above the partner's same-named reference. Mirror for short. | `smt_enabled=False` |
| R26 | Pass criteria | **Not defined by the spec.** Must be decided by the user before any development run (proposal to follow in the review). | — |

## 4. Module layout (Python)

`src/v17/smc_sb/`: `config.py`, `data.py` (loading, guards, candles, integrity), `session.py`, `market_bias.py`,
`liquidity.py` (PDH/PDL, Asian, NWOG, targets), `sweep.py`, `structure.py` (pivots, MSS), `fvg.py`,
`premium_discount.py`, `entry_models.py` (Model A, Model B), `execution.py` (fills, exits, costs), `smt.py`,
`engine.py` (per-day pipeline, event log, trade records), `matched_random.py`.
Every stage returns either an object or a rejection reason; the engine records both.

## 5. Order of work

1. This spec committed.
2. Code + deterministic unit and regression tests (session boundaries, DST, missing candles, FVG formation, MSS
   confirmation, limit fills, stop/target ordering).
3. Data-integrity audit of the development data (no strategy execution).
4. Reproducibility report.
5. **Stop for review.** After sign-off: independent re-implementation match + hand-check, then the baseline
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
