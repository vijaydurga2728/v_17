# Silver Bullet 6-Engine Doctrine Test — Frozen Design Specification

**Document ID:** `docs/superpowers/specs/2026-11-03-silver-bullet-6-engine-doctrine-test-design.md`
**Date:** 2026-11-03
**Status:** FROZEN. No design changes permitted after user approval of this document and before gate completion. Any change invalidates the Monte Carlo Permutation Test (MCPT) p-values and requires a full reset with a new sealed holdout.
**Rulebook of record:** `research/ict/ICT_STRATEGY_RULEBOOK.md` (SOURCE_CONFIRMED / SOURCE_INTERPRETATION / RESEARCH_HYPOTHESIS classified).
**Master context:** `research/MASTER_REVAMP_PLAN.md`.

---

## 1. Purpose and Verdict Framework

Build and run an unbiased statistical test of whether the ICT Silver Bullet strategy, as written in the frozen rulebook, exhibits a non-random edge on the user's historical FX and index data under FTMO Challenge $10,000 Standard account constraints.

The test produces one of three verdicts per engine:

- **PASS:** per-engine MCPT p < 0.0056 AND sealed holdout retains positive expectancy AND portfolio-layer second MCPT passes.
- **FAIL:** any gate fails. Engine is dead for this cycle.
- **ABORT:** data or methodology error detected mid-run. Fix bug, re-run from last clean checkpoint. Does not count as curve-fit so long as rules remain unchanged.

System-level verdict:
- **DEPLOY:** at least one engine PASS AND portfolio layer PASS.
- **SHELVE:** zero engines PASS or portfolio layer FAIL.

Deploy is to FTMO demo for 90 days of live-with-journal observation per Mode 1.5 (Section 11), then FTMO Challenge if demo tracks backtest.

**This specification does not promise profitability. It specifies the honest test.**

---

## 2. Scope Locks (Freeze Table)

All items below are frozen at approval time. Changes mid-cycle invalidate MCPT.

| # | Item | Lock Value | Rationale |
|---|------|-----------|-----------|
| L1 | Setup | Silver Bullet (Model B) | User-selected, Section-4 of rulebook. |
| L2 | Judas Swing scope | **Excluded this cycle** | Deferred to future cycle. |
| L3 | Windows | London 03:00-04:00 NY, NY AM 10:00-11:00 NY, NY PM 14:00-15:00 NY | Rulebook SB-01. |
| L4 | Entry models | Model 1 Conservative (CE 50% FVG midpoint) AND Model 2 Aggressive (proximal edge L_3/H_3) — both run as independent engines | Rulebook SB-04. |
| L5 | Total engines | 6 (3 windows × 2 entries) | L3 × L4. |
| L6 | Symbols | Per rulebook SB-01 per-window eligibility (London: EURUSD, GBPUSD; NY AM: USATECHIDXUSD, EURUSD, GBPUSD; NY PM: USATECHIDXUSD) | Rulebook SB-01. |
| L7 | D1 bias filter | Mirror JS-02: D1 structure (HH/HL vs LH/LL) + D1 EMA20 alignment. If structure opposes EMA20 → NO_BIAS → day idle. | Added as SOURCE_INTERPRETATION; see Section 4. |
| L8 | Parameter training | ZERO. All rulebook parameters frozen at defaults ex-ante. | Section 5. |
| L9 | Walk-forward | 7-fold anchored expanding, yearly OOS blocks | Section 6. |
| L10 | Dev data window | 2015-01-01 → 2024-12-31 UTC | Common availability across SB-eligible instruments. |
| L11 | Holdout window | 2025-01-01 → 2026-10-18 UTC, sealed, single-shot per engine | Section 6. |
| L12 | MCPT | 1000 permutations per engine, block bootstrap, block size = 1 trading week | Section 7. |
| L13 | Significance | Bonferroni-corrected per-engine p < 0.00933 (0.05 / 6 engines, inside dev MCPT). Second MCPT on portfolio-layer p < 0.05 (one test). | Section 7. Note: earlier conversational "p < 0.0056" rounded for simplicity; exact Bonferroni is 0.05/6 = 0.00833. Spec uses the exact value. |
| L14 | Cost model | Bid/ask paired bars, measured per-minute spread, FTMO Standard commissions ($3/lot/side FX, $0 indices), fixed 0.5 pip FX / 0.5 pt USATECH market-order slippage, zero slippage on limit fills, Wednesday ×3 swap if position open across 17:00 NY (SB closes same day, so this is engineering safety not a cost driver). | Section 8. |
| L15 | Cost stress | OOS re-run at 1.5× historical spread. PF ≥ 1.1 required. | Section 8. |
| L16 | FTMO account | Challenge $10,000 Standard. 10% Phase-1 profit target, 5% Phase-2, 5% daily loss, 10% total loss. | User-selected. |
| L17 | Risk per trade | 0.5% equity ($50 at $10k) | User-selected. |
| L18 | Risk circuit breakers | Daily -4% soft stop (flat all, freeze until 00:00 NY). Total -8% hard freeze (manual review). | Section 9. |
| L19 | Concurrency | Phase A (MCPT): each engine independent, up to 6 concurrent positions theoretical. Phase B (portfolio second MCPT): one-position-per-symbol globally, first-trigger-wins priority. | Section 10. |
| L20 | Order type | LIMIT at CE (Model 1) or proximal edge (Model 2). No market entries. Pending expiry = window close + 5 min. | Rulebook SB-04 + default #5. |
| L21 | In-trade management | Static SL per rulebook, static TP opposing-liquidity per SB-05, no trail, no breakeven, no partial. | Default #6. |
| L22 | Session hard exit | Flat all positions at window-end + 60 minutes. Never cross 17:00 NY rollover. | Default #7. |
| L23 | News policy | **Amended 2026-11-03 (post-Task 2.7).** Policy C active: spread-guard only (reject if measured spread > 3× symbol × minute-of-day 30-day median). Policy D (scheduled calendar blackout) deferred — Finnhub free tier returned 403 on `calendar_economic`; calendar source upgrade to Dukascopy news deferred as non-blocking follow-up before any live deployment. Classification of spread-guard-only: `ENGINEERING_CONSTRAINT`. | Section 12. |
| L24 | Audit boundary | Pre-gate audit passes only. No rule changes after any gate run. | Section 13. |
| L25 | Operating mode | Mode 1.5: frozen algo + human monitoring journal, no live overrides. Journal reviewed after 90 days as raw material for a NEW future-cycle engine design, never as a tweak input to this cycle. | Section 11. |
| L26 | OpenAI usage | Pre-build rulebook audit, transcript distillation, post-trade narrative generation, bug-detector anomaly scans. **Prohibited: pre-trade decision filter, live rule tuning.** | Section 14. |

---

## 3. Rulebook Integration

This specification does not restate the rulebook. The rulebook is `research/ict/ICT_STRATEGY_RULEBOOK.md`, which is itself frozen. All SB-01..SB-05 and P-01..P-04 rules apply as written.

### 3.1 Rules referenced from existing rulebook

| Rule | Role in this cycle |
|------|-------------------|
| P-01 | NY midnight anchor for daily cycle (bias/sweep eligibility reference). |
| P-02 | Power of Three (AMD) context framing. Not a direct gate for SB; informational. |
| P-03 | MSS/BOS. Required for structural swing identification. |
| P-04 | FVG mathematical definition + CE formula. Required for SB-04 entries. |
| SB-01 | Window × symbol eligibility matrix. |
| SB-02 | Eligible liquidity pools (no Asian fallback, no PDH/PDL rescue). |
| SB-03 | Displacement criteria: body ratio ≥ 0.65, range ≥ 1.5 × ATR_14(M1), FVG created. |
| SB-04 | Entry: CE (Model 1) OR proximal edge (Model 2). Cost gate: FVG height ≥ 2 × spread. |
| SB-05 | Opposing-liquidity target; structural fallback 15 pts USATECH / 20 pips FX; R:R ≥ 1.5 reject. |

### 3.2 Addendum rule introduced by this spec

**SB-A1: Daily Bias Filter (SOURCE_INTERPRETATION).**
- Mirror of JS-02 Rule applied to Silver Bullet. Classification: `SOURCE_INTERPRETATION`.
- Rationale: ICT doctrine states HTF bias governs all low-timeframe setups. JS-02 formalizes this for Judas Swing. SB rulebook section is silent. Applying the same filter to SB is a doctrine-consistent extension.
- Algorithmic rule (identical to JS-02):
  1. D1 structure: last 20 D1 bars classified as Bullish (HH/HL), Bearish (LH/LL), or Mixed.
  2. D1 EMA20 alignment: Close_D1 > EMA20_D1 → Bullish; Close_D1 < EMA20_D1 → Bearish.
  3. If structure and EMA alignment agree → BIAS = direction.
  4. If structure and EMA alignment disagree OR structure is Mixed → BIAS = NONE. Engine idle for that calendar day.
- Transcript citation: Market Structure Lesson 14 (Keys To Daily Bias). Same primary source as JS-02.
- Operational: BIAS evaluated at 00:00 NY using data strictly before 00:00 NY. No lookahead.

### 3.3 Audit 1 reclassification note (added 2026-11-03)

Audit 1 (`research/audits/rulebook_vs_transcript_2026-11-03.md`) found that cited transcript backing in `ICT_STRATEGY_RULEBOOK.md` was substantially unverified: zero of thirteen citation-instances passed clean, including all four core Silver Bullet rules whose cited "2023 Silver Bullet Lecture" transcript is absent from the user's corpus.

Classifications have been corrected per the audit's "Proposed corrections" (commit `347baa1`). The spec's gate framing is reinterpreted accordingly:

- **Original framing:** "Does the rulebook, as faithfully transcript-cited ICT doctrine, exhibit a non-random edge?"
- **Revised framing:** "Does this specific empirical heuristic set — widely-circulated ICT practice as encoded in the rulebook — exhibit a non-random edge on the user's data?"

Statistical infrastructure (6-engine catalog, dual-scheme MCPT at Bonferroni α=0.00833, sealed holdout, portfolio-layer second MCPT, cost model, risk constraints) is unaffected. Only the interpretive label on the verdict shifts.

The reclassification is applied once, pre-gate. No further rulebook changes are permitted before gate completion (spec §13.2 and §18 unchanged).

### 3.4 Rules audit obligation

Before any code is written against the rulebook, three audit passes run (Section 13). Any legitimate transcript-cited correction found by the audit is applied to the rulebook and this spec is amended in-place prior to approval. Once this spec is approved by the user, the rulebook and this spec are both frozen.

---

## 4. Engine Catalog

Six independent engines. Each has its own state machine, its own trade log, its own equity curve, its own MCPT.

| Engine ID | Window | Entry Model | Eligible Symbols |
|-----------|--------|-------------|------------------|
| SB-LDN-CE | 03:00-04:00 NY | Model 1 CE | EURUSD, GBPUSD |
| SB-LDN-AG | 03:00-04:00 NY | Model 2 Aggressive | EURUSD, GBPUSD |
| SB-NYAM-CE | 10:00-11:00 NY | Model 1 CE | USATECHIDXUSD, EURUSD, GBPUSD |
| SB-NYAM-AG | 10:00-11:00 NY | Model 2 Aggressive | USATECHIDXUSD, EURUSD, GBPUSD |
| SB-NYPM-CE | 14:00-15:00 NY | Model 1 CE | USATECHIDXUSD |
| SB-NYPM-AG | 14:00-15:00 NY | Model 2 Aggressive | USATECHIDXUSD |

An engine may trade multiple eligible symbols concurrently in Phase A (MCPT). In Phase B (portfolio second MCPT), one-position-per-symbol priority applies globally across all 6 engines.

---

## 5. Parameter Freeze Table

All parameters are fixed from rulebook defaults at this spec's approval time. **No per-fold refit. No "regime adaptation". No "expert tweak".**

| Parameter | Value | Source |
|-----------|-------|--------|
| D1 EMA period | 20 | JS-02 / SB-A1 |
| D1 structure swing lookback | 20 D1 bars | Default #1 |
| ATR period (M1) | 14 | SB-03 |
| Displacement body ratio minimum | 0.65 | SB-03 |
| Displacement range multiplier | 1.5 × ATR_14 | SB-03 |
| FVG cost-viability | ≥ 2 × current spread | SB-04 |
| Opposing-liquidity scan window | Current session only | SB-05 |
| Structural fallback target (USATECH) | 15 index points | SB-05 |
| Structural fallback target (FX) | 20 pips | SB-05 |
| Minimum R:R | 1.5 | SB-05 |
| SL buffer (FX) | 1 pip beyond extreme, min 2 pips, max 15 pips | JS-06 pattern applied |
| SL buffer (USATECH) | 2 pts beyond extreme, max 20 pts | Doctrine-consistent extension |
| Pending order expiry | window end + 5 min | Default #5 |
| Position hard exit | window end + 60 min, never cross 17:00 NY | Default #7 |
| News blackout window | -10 min / +20 min around High-impact USD/EUR/GBP | Default #4 |
| Spread-guard median lookback | 30 calendar days per symbol per minute-of-day | Default #3 |
| Spread-guard rejection multiplier | 3× median | Default #3 |
| Daily loss circuit breaker | -4% equity | Default #8 |
| Total loss circuit breaker | -8% peak equity | Default #9 |
| Risk per trade | 0.5% equity | L17 |

---

## 6. Walk-Forward and Holdout Architecture

### 6.1 Data split

- **Dev data:** 2015-01-01 00:00 UTC → 2024-12-31 23:59 UTC. 10 calendar years.
- **Holdout:** 2025-01-01 00:00 UTC → 2026-10-18 00:00 UTC. ~21.5 calendar months. Sealed.

Holdout is not loaded into any dev-phase process. The ingest pipeline tags it with `partition=holdout` and the WF harness refuses to read it under any dev-phase flag. Load gate controlled by a single environment variable `V17_HOLDOUT_UNSEAL=1` set only once per engine during the holdout runner (Section 6.4).

### 6.2 Walk-forward folds (dev data only)

Anchored expanding windows, yearly OOS blocks.

| Fold | Train (anchored) | OOS |
|------|-----------------|-----|
| 1 | 2015-01-01 → 2017-12-31 | 2018-01-01 → 2018-12-31 |
| 2 | 2015-01-01 → 2018-12-31 | 2019-01-01 → 2019-12-31 |
| 3 | 2015-01-01 → 2019-12-31 | 2020-01-01 → 2020-12-31 |
| 4 | 2015-01-01 → 2020-12-31 | 2021-01-01 → 2021-12-31 |
| 5 | 2015-01-01 → 2021-12-31 | 2022-01-01 → 2022-12-31 |
| 6 | 2015-01-01 → 2022-12-31 | 2023-01-01 → 2023-12-31 |
| 7 | 2015-01-01 → 2023-12-31 | 2024-01-01 → 2024-12-31 |

**Important:** Because parameter training is zero (L8), the "train" window is used only for calibrating per-symbol per-minute-of-day spread medians (news policy spread-guard) and the volatility reference bands (ATR history), not for strategy fitting. No parameter is adjusted from one fold to the next.

### 6.3 Dev-phase MCPT (per engine, aggregated OOS)

Per engine:
1. Concatenate per-fold OOS trade series into one chronological trade sequence (2018-01-01 → 2024-12-31).
2. Compute observed statistics: Sharpe, PF, max drawdown, trade count, R² of equity curve linearity, win rate, average R multiple.
3. Permutation null:
   - Block bootstrap. Block size = 1 trading week (Mon-Fri grouped).
   - For each of 1000 permutations, shuffle entry signals within the OOS window (preserving per-bar market data). Alternative: resample trade P&L signs via block bootstrap over trade sequence. **Chosen primary: shuffle entry trigger timestamps within same minute-of-day distribution to preserve session structure. Fallback / sanity test: naive P&L block bootstrap.**
   - For each permutation, re-run the full engine logic and compute the same statistics.
4. p-value per statistic = fraction of permutations with permuted Sharpe (or PF) ≥ observed value.
5. Gate: `p_sharpe < 0.00833 AND p_pf < 0.00833` (both conditions, Bonferroni across 6 engines means we need 0.05/6 = 0.00833).
6. Secondary dev-phase gates (hard, independent of p-value, ALL must pass):
   - **G1 Profit Factor:** aggregated OOS PF ≥ 1.3.
   - **G2 Trade count floor:** total trade count across all 7 folds ≥ 50. If an engine fires < 50 total trades over 7 years of OOS, sample is too small to trust — INCONCLUSIVE verdict.
   - **G3 Per-fold robustness:** no individual fold has net negative P&L. One losing year disqualifies the engine (edge should survive one yearly regime; losing fold = regime fragility).
   - **G4 Equity curve linearity:** R² of linear fit on cumulative P&L curve ≥ 0.80.
   - **G5 Cost stress:** OOS re-run at 1.5× historical spread retains PF ≥ 1.1.

Engine passes dev MCPT only if all primary and secondary gates pass.

### 6.4 Holdout runner (single-shot per engine)

Each engine that passes dev MCPT is tested once on the sealed holdout. One run. One verdict.

- Config: same parameters, same rulebook, same cost model, same news/spread policy.
- Trade count minimum on holdout: 20 trades. Fewer → ABORT (insufficient sample on holdout; engine marked INCONCLUSIVE, not PASS, not FAIL).
- Pass criteria: positive expectancy, PF ≥ 1.2 (slightly relaxed from dev 1.3 given smaller sample), max drawdown ≤ 8% equity, equity curve direction consistent with dev OOS.
- No MCPT on holdout alone (sample too small for 1000-perm block bootstrap to be powered). Holdout serves as live-simulation sanity, not statistical test.

If an engine fails holdout, it is dead. No tuning permitted.

### 6.5 Portfolio layer (second MCPT, Phase B concurrency)

If ≥ 1 engine passes dev MCPT + holdout:
1. Compose a blended equity curve from all passing engines under Phase B concurrency rules (L19: one-position-per-symbol globally, first-trigger-wins).
2. First-trigger priority rule: within a symbol, if two engines trigger within the same M1 bar, priority is: lower window ordinal (03 before 10 before 14), then CE before Aggressive. Deterministic, specified pre-run.
3. Run MCPT 1000 on the blended curve (same methodology as 6.3) over full dev OOS 2018-2024.
4. Gate: single-test p < 0.05 (no Bonferroni; one test). PF ≥ 1.3. R² ≥ 0.80. Max drawdown ≤ 8% equity.
5. Blend tested on holdout once. Must also show positive expectancy on holdout under Phase B rules.
6. Pass → system DEPLOY. Fail → system SHELVE (even if individual engines passed Phase A).

The portfolio gate is deliberately strict because the real FTMO account will enforce one-position-per-symbol in effect (hedging bans + sanity), so the blended curve is the only equity curve that matters for live.

---

## 7. MCPT Methodology

### 7.1 Permutation design

Two complementary permutation schemes run in parallel; both must agree (p < 0.00833 under scheme 1 AND p < 0.00833 under scheme 2 at Bonferroni) for a per-engine pass. This is the strictest honest form; any single scheme can be fooled by its own weakness.

- **Scheme 1 — Signal-time permutation (primary).** For each permutation: within each calendar day's session window, replace the engine's actual entry trigger timestamps with timestamps drawn uniformly at random from the eligible bars of that same window (same symbol, same window, same day). Direction (long/short) is kept consistent with the day's D1 bias so bias-conditional structure is preserved. Market OHLCV data is unchanged. The permuted engine then uses the same SL/TP rules against the real market data. The null hypothesis: "a random entry during the SB window, in the direction of D1 bias, produces equivalent statistics." A real edge rejects this null.
- **Scheme 2 — P&L block bootstrap (sanity).** Trade P&L signs permuted via block bootstrap (block = 1 trading week). Tests whether realized trade outcomes could be due to a lucky streak.

Both schemes 1000 permutations each. Compute runtime budget: ~24-48 CPU hours total across 6 engines at scheme × 1000.

### 7.2 Statistics computed per permutation

Sharpe (annualized, risk-free rate = 0), Profit Factor, Maximum Drawdown, Trade Count, Win Rate, Average R multiple, Equity curve R² of linear fit on cumulative P&L.

### 7.3 Multiple comparison correction

- Within one engine, two statistics (Sharpe and PF) must both pass. Bonferroni-within-engine not applied (same hypothesis measured two ways, not independent comparisons).
- Across 6 engines, Bonferroni: α = 0.05 / 6 = 0.00833 per engine.
- The portfolio-layer test is a single test on a single blended curve → α = 0.05, no further correction.

### 7.4 Reproducibility requirements

- Deterministic seed per permutation: `seed = f(engine_id, scheme_id, permutation_index)` using SHA-256 of a documented seed string.
- All MCPT results written to `research/results/mcpt/<engine_id>/<scheme_id>/results.parquet` with full per-permutation statistics for auditability.
- Any re-run with same inputs must produce identical results. If re-run produces different results, treat as code bug, locate, fix, re-run. Non-determinism is an ABORT condition.

---

## 8. Cost Model Specification

### 8.1 Bid/ask paired bar ingest

Dukascopy-sourced CSVs are paired per instrument: one bid file, one ask file, both EET-timezone 1-minute bars with OHLCV. Ingest pipeline joins them on `time (EET)` and converts to UTC.

Per-bar output schema (Parquet):
```
ts_utc (int64 nanoseconds UTC), symbol (categorical),
bid_o, bid_h, bid_l, bid_c (float64),
ask_o, ask_h, ask_l, ask_c (float64),
bid_volume, ask_volume (float64),
spread_mid (float64 = ask_c - bid_c)
```

Fill mechanics:
- Long entries fill against ASK OHLC on the entry bar.
- Short entries fill against BID OHLC.
- Long exits fill against BID OHLC.
- Short exits fill against ASK OHLC.
- Round-trip spread paid in full on every trade, from real measured ask-bid delta at the actual bars of entry and exit.

### 8.2 Commission

FTMO Challenge Standard commission schedule:
- Majors FX (EURUSD, GBPUSD): $3.00 per standard lot (100,000 units) per side. Round-turn: $6.00/lot.
- USATECHIDXUSD: $0 commission (built into spread for cash indices on FTMO).

Commission computed per-trade in USD and deducted from trade P&L.

### 8.3 Slippage

- Limit orders: zero slippage. If price touches limit, fill assumed at limit price. If not touched, no fill.
- Market orders: 0.5 pip FX, 0.5 pts USATECH, always adverse. (Note: SB engines use LIMIT per L20, so slippage applies only to emergency exits via market order at session hard-exit.)

### 8.4 Swap

Triple-swap on Wednesday 17:00 NY applied only if a position straddles that timestamp. SB engines close same day (window end + ≤ 60 min, always before 17:00 NY), so swap should never apply. Implemented as safety check: if logic ever leaves a position open across 17:00 NY, log as `WARN: unexpected overnight` and apply triple-swap. Fire of this warning in dev run is a bug, not a cost signal.

### 8.5 Cost stress test (OOS re-run)

After primary MCPT, re-run full OOS 2018-2024 with historical spread multiplied by 1.5× per bar. Commission and slippage unchanged. New equity curve computed. Must retain PF ≥ 1.1. Report delta vs base. This is pure stress; not a separate MCPT.

---

## 9. Risk and FTMO Compliance

### 9.1 Account configuration

FTMO Challenge $10,000 Standard. Starting balance $10,000.
- Phase 1 profit target: 10% ($1,000). Minimum 4 trading days.
- Phase 2 (Verification) profit target: 5% ($500). Minimum 4 trading days.
- Daily loss limit: 5% ($500 from each day's start-of-day equity).
- Total loss limit: 10% ($1,000 from initial $10,000 OR from peak high-water-mark balance after funded; backtest uses starting-balance 10% floor).

### 9.2 Risk per trade and sizing

0.5% equity = $50 risk per trade at starting balance.

Position size calculation (per trade, per symbol):
```
size_lots = (equity * 0.005) / (sl_distance_in_price * pip_value_per_lot)
```
Rounded down to broker lot step (0.01 lots).

If computed size < minimum lot (0.01), skip trade (log as `SIZE_FLOOR_SKIP`).

### 9.3 Circuit breakers

- **Daily loss -4%:** at any time intraday, if realized + floating P&L drops below -4% of start-of-day equity, flat all positions at market, freeze engines until 00:00 NY next calendar day. 1% buffer below FTMO 5% hard limit.
- **Total loss -8% from peak:** permanent engine freeze. Manual review required. 2% buffer below FTMO 10% hard limit.

### 9.4 FTMO consistency rule compliance (future-live only)

FTMO funded accounts enforce a payout consistency rule: no single day may exceed 30% of total profit for a payout cycle. Backtest and challenge phases do not enforce this. Live-funded deployment is out of scope for this cycle; a future spec will address consistency-rule-aware trade filtering if the system reaches live-funded status.

---

## 10. Concurrency and Portfolio Composition

### 10.1 Phase A — Per-engine MCPT isolation

Each engine runs standalone. Up to 6 simultaneous positions possible (one per engine, assuming all engines fire). Equity curve per engine computed from that engine's trades only, using full starting equity ($10,000) as if that engine owned the account. Phase A tests whether each engine has an edge against a null hypothesis of random entries within its own session structure.

### 10.2 Phase B — Portfolio composition (post-pass gate)

If one or more engines pass Phase A dev MCPT + holdout, portfolio layer runs:
- One-position-per-symbol globally, across all 6 engines. If engine X is long EURUSD, no other engine may enter EURUSD until X is flat.
- First-trigger-wins priority: within a symbol, if two engines trigger in the same M1 bar, priority order is deterministic:
  1. Lower window ordinal first: London (03) → NY AM (10) → NY PM (14).
  2. Within same window, CE before Aggressive.
- Combined equity curve is the equity curve of a single FTMO account where all passing engines share the account under the priority rule.
- Portfolio MCPT (Section 6.5) runs on the combined curve, dev OOS 2018-2024.
- Portfolio holdout runs on combined curve, 2025-01 → 2026-10.

### 10.3 Why Phase B is the real test

The FTMO account is one account. All trades land on one equity. Hedging restrictions and sanity dictate one-position-per-symbol. The portfolio curve is the only equity curve that matters for live deployment. Phase A exists solely to measure per-engine edge in isolation (statistical cleanliness). Phase B exists to measure the actual deployable system.

---

## 11. Operating Mode: 1.5 (Frozen Algo + Monitoring Journal)

### 11.1 Live-phase behavior

- Algo runs mechanically. No human overrides. No skipped trades, no added trades, no size adjustments.
- Daily dashboard (built as part of implementation) shows: D1 bias state per instrument, planned window times, active FVGs and their CE levels, pending orders, open positions, daily P&L vs circuit-breaker thresholds, FTMO target progress.
- User reviews the dashboard. User writes a daily journal entry capturing their gut reaction, perceived setups the algo missed, perceived bad trades the algo took, emotional state, any external context (news they saw, market tone).
- User does NOT touch the account. The algo is autonomous.
- 90-day journal review: after 90 trading days, aggregate journal + algo trade log, compare "trades user would have skipped" vs actual algo outcomes. If a reliable pattern emerges, it becomes raw material for a FUTURE-cycle engine design, not a tweak to this cycle. Any such new engine must start a fresh cycle with its own sealed holdout.

### 11.2 Hard exclusions

- No OpenAI pre-trade filter.
- No "expert agent" rule tuning post-gate.
- No parameter re-fit based on live results.
- No live rule patches during the 90-day monitoring period (bug fixes to the IMPLEMENTATION are allowed if a bug is proven; rule changes are not).

---

## 12. News Policy — **Amended 2026-11-03: Policy C active, Policy D deferred**

### 12.0 Amendment summary (2026-11-03)

Task 2.7 (Finnhub backfill execution) was BLOCKED by the Finnhub free tier: every `calendar_economic` request returned `FinnhubAPIException(status_code: 403): You don't have access to this resource.` across 2015-2020 chunks. The free tier does not include the economic calendar endpoint.

Resolution (user-approved): downgrade this cycle's news policy from Policy D (scheduled blackout + spread guard) to **Policy C only (spread-based implicit filter)**. Classification: `ENGINEERING_CONSTRAINT` (constrained by data-source availability, not by rulebook or research choice).

Rationale: spread-guard empirically catches most news-induced spread spikes within seconds (news causes bid/ask widening immediately). Policy D remains the correct destination but is non-blocking for the gate run — adding Dukascopy-sourced calendar as a Policy D upgrade before live deployment is a deferred follow-up (Task 2.7-FOLLOWUP, out of scope for the current gate cycle).

### 12.1 Calendar source — DEFERRED

Finnhub free tier blocked (403 on `calendar_economic`). Dukascopy historical news export is the recommended future source and matches the bar-data origin. No calendar ingested in this cycle.

### 12.2 Scheduled blackout — DEFERRED

Scheduled blackout windows require a populated calendar parquet and are not enforced in this cycle.

### 12.3 Spread-based reject — **ACTIVE (Policy C)**

Per symbol, per minute-of-day (1440 buckets), rolling 30-calendar-day median of measured spread computed from paired bid/ask bars. At entry evaluation time, if current spread > 3 × median → reject entry (log as `SPREAD_SPIKE_REJECT`).

This is the ONLY news/spike filter applied in this cycle. All gate runs use Policy C only.

### 12.4 Combined effect — N/A this cycle

Only the spread guard applies. The "combined AND" design is restored in a future cycle once a real calendar source is ingested.

### 12.5 Gate verdict interpretation adjustment

If the gate passes with Policy C only, the verdict reads "edge survives spread-guard-only news filtering." A conservative interpretation then runs a sensitivity study (post-pass, non-gate) adding a Dukascopy-sourced blackout retrospectively to confirm the edge does not come exclusively from news-driven moments.

---

## 13. Audit Boundary

### 13.1 Pre-gate audit passes (mandatory, blocking)

Three independent audits run after this spec is approved and BEFORE any gate runs. Each produces a written finding list. Any finding that identifies a transcript-cited correction, a code implementation defect, or a methodology flaw must be fixed before proceeding. Corrections at this stage are not curve-fit; they are bug fixes against doctrine or math.

**Audit 1 — Rulebook vs transcript.**
- Agent: specialist research agent dispatched over `C:\personal\ICT transcript\` (ict2022, OTE, market_structure directories).
- Scope: every `SOURCE_CONFIRMED` and `SOURCE_INTERPRETATION` rule in `research/ict/ICT_STRATEGY_RULEBOOK.md` cross-checked against its cited transcript section. Timestamps verified. Quoted strings verified.
- Output: `research/audits/rulebook_vs_transcript_2026-11-03.md`.
- Discrepancy policy: any mismatch is corrected in the rulebook with new citation. Spec amended if the correction changes a parameter in Section 5.

**Audit 2 — Code vs rulebook.**
- Agent: `python-reviewer` + `understand-anything:understand` applied to `src/v17/setups/silver_bullet_fsm.py`, `src/v17/structure/`, `src/v17/risk/` after implementation per Section 15.
- Scope: FSM transitions match SB-01..SB-05. Causality enforced (no lookahead paths). Pip/point scaling correct. Entry/exit prices use correct bid/ask side per L14.
- Output: `research/audits/code_vs_rulebook_<date>.md`.
- Discrepancy policy: fix code to match rulebook. Rulebook is authoritative over code.

**Audit 3 — Methodology.**
- Agent: `agent-skills:test-engineer` + manual review of MCPT harness, WF split, Bonferroni math.
- Scope: block bootstrap correctness, seed determinism, Bonferroni α correction, holdout seal enforcement.
- Output: `research/audits/methodology_<date>.md`.
- Discrepancy policy: fix harness. Rulebook unaffected.

### 13.2 Post-gate rule changes

**None permitted.**

If all engines fail gate:
- Option A — SHELVE this cycle. Honest outcome. Move on.
- Option B — Declare curve-fit cycle: user acknowledges in writing that subsequent runs are not statistically valid; results are discretionary research, not science.
- Option C — Full reset: new rulebook designed from scratch, new sealed holdout window (would require data not yet observed in prior gate; practically means waiting for new data or using a longer-ago sealed slice).

The system does not permit "small adjustments" to the rulebook after a failed gate.

---

## 14. OpenAI API Usage

### 14.1 Permitted uses

1. **Rulebook audit:** feeding transcript sections + rule claims for mismatch detection (Audit 1).
2. **Transcript distillation:** processing uncited transcript sections to surface new rule candidates (which, if introduced, require new citation + classification + spec amendment pre-gate).
3. **Post-trade narrative:** auto-generating plain-English summaries of closed trades from the structured trade log. Purely descriptive output; influences nothing.
4. **Bug detector:** anomaly scan over trade logs for "trade violated rulebook constraint" (e.g., opened against D1 bias; opened outside window; FVG height violated cost-viability gate). Flags surface as code bugs for human review.
5. **Research assistant:** pre-build literature survey on ICT backtesting failure modes, academic SMC research, GitHub open-source backtester patterns.

### 14.2 Prohibited uses

1. Pre-trade decision filter of any kind.
2. Live rule tuning or parameter adjustment.
3. Any role in gate-time decisions (MCPT, holdout, portfolio).
4. Any role in post-gate re-interpretation of results.

### 14.3 Model version pinning

Where OpenAI is used, model string is pinned (e.g., `gpt-4-turbo-2024-04-09`) and recorded in output artifacts. If OpenAI deprecates the pinned model, the pinned artifact remains the record; new runs with a newer model are classified as a different analysis.

---

## 15. Deliverables and Timeline

### 15.1 Phases

| Phase | Deliverable | Est. hours |
|-------|------------|-----------:|
| P1 | Finnhub calendar backfill 2015-2026 → `data/calendar/economic_events.parquet` | 10 |
| P2 | Dukascopy CSV ingest pipeline → `data/bars/<symbol>/{bid,ask}.parquet` + spread derivation | 25 |
| P3 | Audit 1 — rulebook vs transcript | 15 |
| P4 | Spec amendment (if Audit 1 flags corrections) + user re-approval | 5 (contingent) |
| P5 | FSM implementation: Silver Bullet with D1 bias filter, 6 engine configurations | 40 |
| P6 | Audit 2 — code vs rulebook | 15 |
| P7 | Walk-forward harness, 7-fold anchored, Bonferroni-aware | 20 |
| P8 | MCPT harness, dual-scheme, 1000 permutations each, deterministic seeds | 25 |
| P9 | Audit 3 — methodology | 10 |
| P10 | Dev-phase MCPT run across 6 engines, cost stress rerun | 30 (compute) + 10 (analysis) |
| P11 | Holdout runner (single-shot per passing engine) | 10 |
| P12 | Portfolio-layer composition + second MCPT | 20 |
| P13 | Final gate report, verdict document, Mode 1.5 dashboard spec | 15 |

Total estimate: ~250 hours engineering + ~30 hours compute wait. At 20 hours/week, calendar duration 10-13 weeks assuming no major audit findings.

### 15.2 Checkpoints

User sign-off required at:
- Approval of this spec (before P1).
- Approval of Audit 1 findings and any resulting rulebook amendments (before P5).
- Review of final gate report (before any FTMO demo deployment).

---

## 16. Non-Goals

The following are explicitly out of scope for this cycle:

- Judas Swing (Model A). Deferred to a separate future cycle with its own sealed holdout.
- Other ICT setups (Unicorn, Breaker, PO3, SMT, OTE Model, 2022 Mentorship Model). Out of scope.
- Any symbol not listed in rulebook SB-01 (USDJPY, EURGBP, NZDUSD, USDCAD, USDCHF, AUDUSD, XAUUSD, BTCUSD, USA30IDXUSD, USA500IDXUSD).
- Live FTMO Challenge deployment. Mode 1.5 demo observation phase precedes any live money commitment and is a separate decision.
- OpenAI pre-trade filter.
- Discretionary override capability.
- Automated rule tuning or regime adaptation.
- Machine learning models of any kind.
- Multi-timeframe HTF confluence beyond D1 bias (no 4H confluence, no weekly bias).

- Reclassification of rules post-gate based on gate results.

Attempting any non-goal mid-cycle requires: full stop, new spec, new sealed holdout, new gate. There is no shortcut.

---

## 17. Honest Expectation of Outcome

Compound probability of system reaching DEPLOY status (one or more engines pass Phase A + holdout + Phase B portfolio MCPT): estimated 8-25% based on retail algorithmic trading base rates adjusted for the quality of the rulebook and the honesty of the gate.

Compound probability of a DEPLOY-status system subsequently passing an FTMO Challenge + Verification + funding and generating positive live P&L: additional multiplicative 30-50% on top of DEPLOY probability.

End-to-end probability of positive live FTMO funded P&L from the start of this cycle: estimated 3-15%.

These numbers are not pessimism. They are survivorship-adjusted base rates. Any system claiming higher is lying or hiding curve-fit. The gate exists to detect curve-fit cheaply, before FTMO fees and real losses.

If this probability range is unacceptable to the user, the correct action is to not run this cycle. Running the cycle and then rejecting the outcome because "it was supposed to work" is the single worst mistake available.

Note: following the Audit 1 reclassification (§3.3), the test is now explicitly framed as an empirical test of widely-circulated ICT heuristics rather than a citation-faithful doctrine test. The probability bands and verdict interpretation remain the same. The honesty of the gate — frozen rules, no training, MCPT, sealed holdout — is unchanged by the reclassification.

---

## 18. Change Control

- This specification is frozen at user approval time (first approval 2026-11-03, re-approval after Audit 1 reclassification 2026-11-03 — see §3.3).
- Pre-approval amendments: inline edits, user re-reviews, no versioning.
- Post-approval: NO AMENDMENTS before gate completion. If a bug is found in SPEC during implementation (e.g., contradiction, undefined behavior), stop, bring it to user, re-decide. Do not amend silently.
- Post-gate: next cycle. New document. New sealed holdout. New gate. This document becomes historical record.

---

## Appendix A — Glossary

- **CE (Consequent Encroachment):** 50% midpoint of a Fair Value Gap. Entry level for SB Model 1 Conservative.
- **FVG (Fair Value Gap):** 3-candle imbalance pattern per Rule P-04.
- **MCPT (Monte Carlo Permutation Test):** permutation-based null-hypothesis test for strategy edge.
- **MSS (Market Structure Shift):** per Rule P-03. Bar close beyond a swing extreme in opposite direction.
- **OOS (Out-of-Sample):** data in a walk-forward test fold not used for any training or calibration.
- **Phase A:** per-engine isolated MCPT, each engine measured as if solo on account.
- **Phase B:** portfolio-layer composed MCPT, all passing engines share one account under one-position-per-symbol priority.
- **PF (Profit Factor):** gross wins divided by gross losses.
- **Sealed holdout:** data partition locked away from all dev-phase processes, touched exactly once per engine at gate time.
- **SB-A1:** new addendum rule introduced by this spec; D1 bias filter for Silver Bullet, SOURCE_INTERPRETATION classification.

---

## Appendix B — Rejected Alternatives (for completeness)

- Testing a single window first (option A in brainstorming). User chose 3 parallel windows.
- Testing a single entry model (option A in entry decision). User chose both as independent engines.
- No bias filter / 4H bias / both-as-engines (SB-A1 alternatives). User chose D1 bias mirrored from JS-02.
- 12-fold quarterly anchored WF / rolling 3Y-1Y / CPCV. User chose 7-fold anchored yearly + holdout.
- Per-fold parameter refit / single calibration on 2015-17. User chose zero training.
- Simple cost model (static spread) / mid-price. User chose institutional bid/ask paired.
- Full engine independence throughout / one-position-per-symbol throughout. User chose two-phase (A then B).
- No news filter / spread-only / blackout-only. User chose combined blackout + spread guard.
- ForexFactory scrape / Investpy / user-provided. User chose Finnhub free API.
- OpenAI pre-trade filter. Discarded as curve-fit vector.
- Pure discretionary mode. Discarded as incompatible with validation.
- Hybrid "fresh daily rule tuning". Discarded as curve-fit by construction.

---

**End of specification. Awaiting user approval.**
