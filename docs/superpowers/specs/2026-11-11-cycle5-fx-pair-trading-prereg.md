# Cycle 5 — FX Pair Trading via Cointegration (FROZEN PRE-REG)

**Status:** DRAFT 2026-11-11 pending user sign-off. FROZEN upon first commit of implementation code.
**Branch:** TBD (`cycle5-fx-pair-trading` suggested, from `ensemble-h1-cycle4`).
**Prior cycles:** SB, ORB, Gap-Fade SHELVED. RSI2-NAS100 live in 30-day demo. RSI(2) FX dead/marginal.

## 1. Thesis

FX majors contain cointegrated pairs where the spread mean-reverts. Trading the spread is **market-neutral by construction** — removes the drift bias that collapsed the long-only equity-RSI(2) design on FX. Published Sharpe on cointegrated FX spreads is 0.5-1.0 (Engle-Granger 1987 and derivatives).

## 2. Universe (LOCKED)

8 FX majors in D1 cache at `data/bars_d1/<SYMBOL>/`:

- EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCAD, USDCHF, USDJPY, EURGBP.

Pair combinations: C(8,2) = **28 candidate pairs**.

## 3. Pair selection — Engle-Granger ADF test (LOCKED)

Run ONCE on dev window (2015-01-01 → 2024-12-31):

1. For each pair (A, B) of the 28 candidates:
   - Fit OLS: `log(B) = α + β·log(A) + ε` on dev data.
   - Run Augmented Dickey-Fuller test on residuals ε (null: unit root = NOT cointegrated).
   - Record ADF p-value.
2. Apply **Bonferroni correction** for the 28 tests: pair passes if ADF p < 0.05 / 28 = **0.00179**.
3. Record β (hedge ratio) and the mean + standard deviation of the residual series per passing pair.

**Pair selection is LOCKED before any trade sim.** No profit-based pair filtering allowed.

## 4. Strategy rules (LOCKED per pair)

For each cointegrated pair with β and residual std σ:

- **Spread definition:** `z_t = (log(B_t) - α - β·log(A_t)) / σ`.
- **Entry:** when `|z_t| >= 2.0`, open a trade:
  - `z_t <= -2.0` → **LONG spread**: buy B, sell β units of A.
  - `z_t >= +2.0` → **SHORT spread**: sell B, buy β units of A.
- **Exit (whichever first):**
  - `|z_t| <= 0.5` (mean reversion).
  - `|z_t| >= 4.0` (stop loss on further divergence).
  - 20 D1 bars elapsed (time cap).

## 5. Risk sizing (LOCKED)

- 0.5% equity per trade = $50 on $10k FTMO Standard.
- Split evenly across legs: each leg risks $25.
- 1R = 1 z-score unit (observed stop at |z|=4 → z-move from entry at 2 to stop at 4 = 2R loss).
- Transaction costs: 0.5 pip slippage per leg per side = 2 pips round-trip per pair-trade.

## 6. Walk-forward (LOCKED)

Same `generate_folds()` as prior cycles — 7 anchored folds, OOS years 2018-2024.

Cointegration test is run on the **full dev set** before fold-splitting. This is defensible because pair selection reflects the long-term structure of FX pairs, not fold-period-specific trade performance. Trade generation IS per-fold OOS as usual.

## 7. Gates (LOCKED, same thresholds)

### Per-pair secondary gates
- G1: PF ≥ 1.3
- G2: trade_count ≥ 25
- G3: every fold net-positive
- G4: R² ≥ 0.80
- G5: cost-stress PF (2× slippage) ≥ 1.1

### Per-pair scheme-1 MCPT
- Random spread-entry null (sample N random z-threshold-crossings from eligible dates).
- Test statistic: mean_r (NOT PF — same reasoning as cycle 4B).
- α = 0.05 / k where k = number of cointegrated pairs passing section 3.
- 500 permutations per window.

### Portfolio holdout
- Only pairs passing per-pair G1-G5 AND scheme-1 advance.
- Holdout window: 2025-01-01 → 2026-10-18.
- Portfolio PF ≥ 1.3 required.
- Max portfolio DD < 6R.
- No FTMO hard-freeze.

## 8. Known failure modes and mitigation

- **Cointegration breakdown:** if a pair's residuals fail an out-of-sample ADF test on 2024 data alone, flag but DO NOT re-select. Document in holdout report.
- **Correlated pairs:** if 3+ pairs share a common currency (e.g., EURUSD + GBPUSD + AUDUSD all vs USD), their trades will correlate. Flag the portfolio risk; do not combine into one position.
- **Over-fitting hedge ratio β:** β is fit on 10 years of dev data. Published literature suggests β on FX is stable; if holdout residuals show β drift > 20%, flag.

## 9. Honest expectation

- Per-pair PF > 1.3 after scheme-1 given 2015-2024 regime: **20-35% per pair**.
- Expected qualifying pairs out of ~5-10 passing cointegration: **1-3**.
- Portfolio holdout PF ≥ 1.3: **30-50%** conditional on ≥ 2 qualifying pairs.
- End-to-end DEPLOY: **10-20%**.
- From DEPLOY to FTMO funded + first payout: **30-50%**.
- **End-to-end: 3-10%.** Higher than ORB cycles due to market-neutral construction; lower than RSI2-NAS100 due to higher complexity and 2-leg execution risk.

## 10. Implementation scope

- C5-S1 (this spec): freeze pre-reg. ~30 min.
- C5-S2: cointegration pair selection script + report. ~1 session.
- C5-S3: pair-trade runner module + tests. ~1 session.
- C5-S4: per-pair secondary gates + scheme-1 MCPT. ~1 session.
- C5-S5: portfolio holdout + verdict. ~0.5 session.

Total: ~4 sessions.

## 11. Non-goals / abort conditions

- Do NOT run on NAS100 or other equity indices (cointegration arguments don't apply).
- Do NOT add intraday timeframes mid-cycle.
- Do NOT re-run cointegration on holdout data to "refresh" pair selection — that is p-hacking.
- Abort the cycle if ZERO pairs clear ADF Bonferroni threshold.
- Abort if FTMO breaker hard-freezes during any dev fold — suggests risk sizing miscalibrated.

## 12. User sign-off checkbox

- [ ] User reviewed sections 2, 3, 4, 5 and confirms parameters are reasonable.
- [ ] User accepts the honest 3-10% end-to-end prior.
- [ ] User confirms no further strategy rule changes after this spec is committed.

Reply "signed" in chat to proceed to C5-S2.
