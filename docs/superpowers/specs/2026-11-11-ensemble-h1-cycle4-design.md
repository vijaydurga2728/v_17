# Ensemble H1 (Cycle 4) — Design Spec (FROZEN)

**Status:** FROZEN 2026-11-11 before any strategy code.
**Branch:** `ensemble-h1-cycle4` (from `orb-reversal-indices`).
**Prior cycles SHELVED:** SB 6-engine (2026-11-10), ORB-Reversal naked + trend-filter (2026-11-11), Gap-Fade (2026-11-11).

## 1. Thesis

Three uncorrelated hedge-fund-grade strategies run as an ensemble across three uncorrelated instruments on H1. Diversification lifts portfolio PF structurally; H1 removes M1 noise that killed earlier cycles; published edges have known-positive priors.

## 2. Instruments (LOCKED)

| ID | Symbol | Class | Correlation to NAS100 |
|---|---|---|---|
| I1 | `EURUSD` | FX major | ~0.1 |
| I2 | `GBPUSD` | FX major | ~0.15 |
| I3 | `USATECHIDXUSD` | Equity index | 1.0 (self) |

H1 cache at `data/bars_h1/<SYMBOL>/<partition>/year=YYYY/`. Dev 2015-01 → 2024-12-31. Sealed holdout 2025-01-01 → 2026-10-18.

## 3. Strategies (LOCKED, published edges, fixed parameters)

### S1 — Time-Series Momentum (Moskowitz, Ooi, Pedersen 2012)

Long if past-N-hour return > 0; short if < 0. Binary sign only, no magnitude scaling.

| Param | Value |
|---|---|
| Lookback | 480 H1 bars (20 trading days ≈ 1 month) |
| Hold period | 120 H1 bars (5 trading days ≈ 1 week), rolling non-overlapping |
| Entry | first H1 bar at or after the hold-period boundary |
| Stop | 2 × ATR_14(H1) from entry, static |
| Target | hold-period exit OR 3R opposite target, whichever first |
| Signal rebalance | every 120 H1 bars; one trade per instrument per rebalance |
| Universe | I1, I2, I3 |

### S2 — Donchian Channel Breakout (Turtle rule 1, H1)

Enter long on close above prior-20-H1 high; short on close below prior-20-H1 low.

| Param | Value |
|---|---|
| Channel length | 20 H1 bars |
| Entry trigger | H1 close breaks prior-20-H1 extreme |
| Stop | opposite-10-H1 channel extreme (trailing) |
| Target | 2R fixed |
| Session filter | none (both FX and index trade full H1 range available in data) |
| Universe | I1, I2, I3 |

### S3 — Connors RSI(2) Mean Reversion (symmetric)

Long when RSI(2) < 10; short when RSI(2) > 90. Stop at 2× ATR_14 adverse; exit on RSI mean-touch or 5-bar time cap.

| Param | Value |
|---|---|
| RSI period | 2 H1 bars |
| Entry long threshold | RSI(2) < 10 |
| Entry short threshold | RSI(2) > 90 |
| Exit | RSI(2) crosses back through 50 OR 5-H1-bar time cap |
| Stop | 2 × ATR_14(H1) adverse |
| Universe | I1, I2 only (FX mean-reverts; index does not per cycle-3 evidence) |

## 4. Engine-instrument matrix (8 pairs, LOCKED)

| Engine | I1 EURUSD | I2 GBPUSD | I3 USATECHIDXUSD |
|---|---|---|---|
| S1 TSM | ✓ | ✓ | ✓ |
| S2 Donchian | ✓ | ✓ | ✓ |
| S3 RSI(2) | ✓ | ✓ | — |

Total: **8 engine-instrument pairs.**

## 5. Risk (LOCKED)

- 0.5% equity per trade, `ORBRiskEngine` with daily -3% soft / total -8% hard.
- 1 open trade per instrument at any time (if S1 is open on EURUSD, S2 EURUSD entry is skipped; priority by engine order S1 > S2 > S3).
- Max 1 new entry per instrument per H1 bar.
- Cost model: spread from `spread_mid` column, slippage 0.5 pts USATECH / 0.5 pips FX majors, FTMO $0 commission.

## 6. Portfolio layer (LOCKED)

- Equal risk weight across pairs (0.5% each, ensemble risk capped at 2% simultaneous).
- No inverse-vol weighting this cycle (adds a free parameter — avoid).
- Portfolio equity curve = sum of per-pair pnl_r × risk weight.

## 7. Walk-forward (LOCKED)

7 anchored folds per `generate_folds()` — OOS years 2018-2024. Each engine-instrument pair evaluated independently on its own fold OOS trades.

## 8. Gates (LOCKED)

### Per-pair secondary gates (same thresholds all pairs)

| Gate | Threshold |
|---|---|
| G1 | PF ≥ 1.3 |
| G2 | trade_count ≥ 25 |
| G3 | every fold PnL (R) > 0 |
| G4 | R² ≥ 0.80 |
| G5 | cost-stress PF (2× slippage) ≥ 1.1 |

### Per-pair MCPT

`run_mcpt(scheme="pnl_bootstrap", n_permutations=500, block_size=5)`. **Bonferroni α = 0.05 / 8 = 0.00625.** A pair passes MCPT only if its PF p-value < 0.00625.

### Portfolio holdout gate

- Only pairs passing per-pair G1-G5 AND MCPT advance.
- Holdout window 2025-01-01 → 2026-10-18.
- Breakers: `ORBRiskEngine(10_000)`.
- Portfolio metrics: PF ≥ 1.3, max_dd_pct < 6%, no hard freeze, portfolio MCPT (1000 permutations) p < 0.05.

### Final verdict

- **DEPLOY** if portfolio passes holdout AND ≥ 2 pairs qualified into portfolio.
- **SHELVE** otherwise.

## 9. Pre-registration discipline

- Every parameter in sections 2-7 is FROZEN at commit of this spec. Any change = new cycle.
- Per-pair failures: shelve that pair, continue with the remaining ensemble.
- Zero rescue filters, zero post-hoc tuning, zero regime-filter additions mid-cycle.

## 10. Honest expectation

- Per-pair pass probability (published edge, 7-fold OOS, with Bonferroni): **15-30%**.
- Expected qualifying pairs out of 8: **1.2-2.4**.
- Portfolio holdout survival: **40-60%** (conditional on ≥ 2 pairs qualifying).
- End-to-end DEPLOY: **15-25%**.
- From DEPLOY to FTMO funded + first payout: **30-50%**.
- **End-to-end (DEPLOY → demo → challenge → funded → first payout): 5-15%**.

Higher than cycles 1-3 because: (a) diversification lifts expected portfolio PF, (b) published strategies have positive EV priors, (c) H1 removes M1 noise, (d) ensemble converts coin-flips to odds.

Still bounded by the base rate. Three prior shelves confirm the base rate asserts itself.

## 11. Session plan

- S1 (DONE 2026-11-11): data port, H1 cache, resample_paired, read_bars_h1.
- S2 (this spec): freeze design; commit before any strategy code.
- S3: TDD S1 TSM module + tests on crafted + EURUSD-only dry run.
- S4: TDD S2 Donchian module + tests.
- S5: TDD S3 RSI(2) module + tests.
- S6: Portfolio runner + 8-pair dev WF.
- S7: Per-pair secondary gates + MCPT.
- S8: Holdout + portfolio verdict + `GATE_MANIFEST.md` entry.

Estimated 7-8 focused sessions. Will not try to run them all in one day.
