# Cycle 4B Correction — P-Hacking Disclosure + Corrected Pre-Reg

**Status:** FROZEN 2026-11-11 before any code change to the 3 strategies.
**Branch:** `ensemble-h1-cycle4`.

## 1. P-HACKING DISCLOSURE (read this to future-you)

The user explicitly requested that the three cycle-4 strategies (TSM, Donchian, RSI(2)) be re-tuned AFTER seeing dev results that failed the per-pair secondary gates. Under standard pre-registration discipline (established in `feedback_prereg_discipline.md`), tuning strategy parameters after seeing dev-data outcomes is p-hacking. The user has accepted this warning in writing (this document).

Consequences future-you must remember:
- Any PF uplift observed after this document was committed carries an unknown amount of look-ahead bias.
- Dev-data PF is now an UPPER BOUND, not an estimate, of holdout performance.
- If this cycle produces a "passing" strategy, the honest prior on it surviving sealed holdout is **cut roughly in half** vs a pre-registered test.
- FTMO challenge decisions must NOT be made on cycle-4B dev PF alone. Only the sealed-holdout + MCPT verdict counts.

**Commit messages for cycle-4B code changes include the tag `[P-HACK-ACKNOWLEDGED]` for audit trail.**

## 2. What this document is NOT

It is not permission to grid-search parameters until dev data looks good. It is not permission to pick-and-choose instruments based on cycle-4 smoke results. It is not permission to run "one more test" after this cycle also fails.

## 3. The corrections (LOCKED, reference-grounded only)

Each change below is grounded in the original published source of the strategy, NOT in the cycle-4 dev-data pattern. Parameters are what the paper/book specifies. No cycle-4 PF numbers informed these values.

### S1 — TSM (Moskowitz, Ooi, Pedersen 2012)

Original paper specifies monthly bars, 12-month lookback, 1-month hold, cross-sectional 58-asset universe with inverse-vol weighting. Full replication requires multi-asset data we do not have. **Minimum-defensible single-instrument adaptation (the paper's time-series arm, not the cross-sectional arm):**

| Param | Cycle-4 value | Cycle-4B value | Reference |
|---|---|---|---|
| Timeframe | H1 | **D1** | Paper time-series specification |
| Lookback | 480 H1 (~1 month) | **252 D1 (~12 months)** | Paper's TSMOM(12,1) base rule |
| Hold | 120 H1 (~1 week) | **21 D1 (~1 month)** | Paper hold period |
| Direction | Binary sign | Binary sign | Unchanged |
| Position sizing | Flat 0.5% | Flat 0.5% | Inverse-vol out of scope — need universe |
| Stop | 2 × ATR_14(H1) | **2 × ATR_14(D1)** | Scale with TF |
| Target | 3R | **None — hold-period exit only** | Paper has no hard target |
| Universe | 3 instruments × 1 engine | Same 3 instruments × 1 engine | Universe gap not solvable this cycle |

**Honest limitation:** the user has constrained the universe to **FX majors and equity indices only** (no commodities, no bonds, no crypto — stated 2026-11-11). This caps the universe at EURUSD + GBPUSD + USATECHIDXUSD = 3 instruments. The Moskowitz paper's cross-sectional diversification Sharpe requires 10+ assets; three correlated-to-USD instruments cannot reproduce it. TSM in cycle-4B is therefore a single-instrument time-series test, not the paper's full edge. If it fails, the failure is attributable in part to the universe cap, and expanding universe later is the honest next move, not p-hacking parameters.

### S2 — Donchian (Turtle rule 1)

Original Turtle rules: daily bars, 20-day breakout entry, 10-day opposite-channel exit, 2N (ATR) stop, pyramid up to 4 units.

| Param | Cycle-4 value | Cycle-4B value | Reference |
|---|---|---|---|
| Timeframe | H1 | **D1** | Turtle spec |
| Entry channel | 20 H1 | **20 D1** | Turtle spec |
| Trail/exit channel | 10 H1 | **10 D1** | Turtle spec |
| Stop | opposite-10-H1 channel | **2 × N (D1 ATR_20)** | Turtle spec |
| Target | 2R fixed | **None — exit on opposite 10-day channel** | Turtle spec (trend-following has no target) |
| Pyramid | None | None (0.5N adds out of scope) | Keep simple; primary edge is entry, not pyramid |

### S3 — Connors RSI(2)

Connors' book: daily bars, SPY/QQQ, RSI(2) < 10 long, exit on close above 5-day SMA, **long-only**. No stop (position is exited on next close over MA).

| Param | Cycle-4 value | Cycle-4B value | Reference |
|---|---|---|---|
| Timeframe | H1 | **D1** | Connors book |
| Instrument | EURUSD, GBPUSD | **USATECHIDXUSD only** (QQQ proxy) | Connors book + FX has no drift bias |
| Direction | Symmetric | **Long-only** | Connors book |
| Entry | RSI(2) < 10 | Unchanged | Connors book |
| Exit | RSI cross 50 OR 5-bar cap OR SL | **Close > SMA(5) OR 10-day time cap** | Connors book + safety cap |
| Stop | 2 × ATR_14 | **None** (uses MA-close exit) | Connors book |

## 3.5 Universe constraint (user directive 2026-11-11)

**Only FX majors and equity indices.** No commodities (XAUUSD, oil), no bonds (TLT), no crypto, no sector ETFs, no DXY as a traded instrument. Available data: EURUSD, GBPUSD, USATECHIDXUSD. If FTMO Standard account later unlocks more indices (SPX500, GER40, JP225, etc.) they can be added in a future cycle — but NOT this one.

## 4. Engine-instrument matrix after corrections

| Engine | EURUSD | GBPUSD | USATECHIDXUSD |
|---|---|---|---|
| TSM-D1 | ✓ | ✓ | ✓ |
| Donchian-D1 | ✓ | ✓ | ✓ |
| RSI2-D1 Long-only | — | — | ✓ |

**7 engine-instrument pairs.** Bonferroni α = 0.05 / 7 ≈ 0.00714.

## 5. Gates (unchanged thresholds)

Same G1-G5 secondary gates (PF ≥ 1.3, trades ≥ 25, all folds positive, R² ≥ 0.80, cost-stress PF ≥ 1.1) plus per-pair MCPT at α = 0.00714 plus sealed-holdout portfolio PF ≥ 1.3.

**Adjusted honest expectation (with p-hack penalty):**
- Base-rate prior for any pair passing dev gates: 25-45% (higher than cycle 4 due to paper-correct implementation).
- After p-hack adjustment (dev PF is upper bound): effective passing prob **15-30%**.
- Portfolio holdout survival if ≥ 2 pairs pass dev: **30-50%** (lower than cycle-4 due to p-hack).
- End-to-end DEPLOY: **5-15%**.
- From DEPLOY to FTMO funded + first payout: **20-40%** (p-hack penalty on edge quality).
- **End-to-end: 1-6%.** Lower than cycle 4's pre-p-hack 5-15% estimate.

## 6. D1 bar availability

All three instruments already have D1-derivable data via `resample_paired(bars_h1, TF.D1)` — the D1 cache can be built from the existing H1 cache at `data/bars_h1/`. No new data sourcing required.

## 7. SHELVE rule (binding)

If after cycle-4B:
- Fewer than 2 pairs pass dev G1-G5 + MCPT at α=0.00714, OR
- The holdout portfolio PF < 1.3 OR max_dd ≥ 6% OR hard-freeze triggered,

the cycle SHELVES PERMANENTLY. No further corrections, no new pre-reg, no "one more cycle" rescue. The whole algo-building thread pauses for at least 2 weeks of break per the fatigue protocol in `project_orb_cycle.md`.

## 8. Session plan

- C4B-S1 (this doc): freeze the correction pre-reg + p-hack disclosure.
- C4B-S2: D1 cache build (resample_paired on H1 cache).
- C4B-S3: rewrite TSM to D1 spec, re-run.
- C4B-S4: rewrite Donchian to D1 spec, re-run.
- C4B-S5: rewrite RSI(2) to D1 long-only NAS100, re-run.
- C4B-S6: formal per-pair gates + MCPT across all 7 pairs.
- C4B-S7: sealed-holdout portfolio verdict + final GATE_MANIFEST entry.

Estimated 5-7 focused sessions.
