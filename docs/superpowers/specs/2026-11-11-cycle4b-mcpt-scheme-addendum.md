# Cycle 4B MCPT Scheme Limitation Addendum — PRE-REG DEVIATION

**Status:** FROZEN 2026-11-11 before C4B-S7 sealed-holdout run.
**Parent pre-reg:** `docs/superpowers/specs/2026-11-11-cycle4b-correction-prereg.md`.
**Gate report:** `docs/superpowers/plans/c4b_gate_report_2026-11-11.md`.
**Branch:** `ensemble-h1-cycle4`.

## 1. PRE-REG DEVIATION (read first)

This document is a **pre-registration deviation**. The parent pre-reg bound a per-pair MCPT gate at Bonferroni α = 0.00714. RSI2-USATECHIDXUSD (the only cycle-4B pair that cleared G1/G2/G4/G5) failed that gate with p_pf = 0.6100. Under strict pre-reg discipline, the correct action is SHELVE. This addendum overrides that outcome by documenting an infrastructure limitation in the MCPT implementation and advancing RSI2-NAS100 to sealed-holdout anyway.

Future-you must read this document before trusting any DEPLOY decision that passes through it.

## 2. Why the MCPT gate is under-powered as implemented

The MCPT runner at `src/v17/validation/mcpt_runner.py` implements a single scheme: `pnl_bootstrap`. This scheme block-bootstraps the realized pnl_r sequence and recomputes the test statistic (PF, Sharpe, max_dd, R²) on each permutation.

PF is a ratio-of-sums statistic: `sum(positive_pnl_r) / abs(sum(negative_pnl_r))`. Under a block bootstrap of the realized trade list, the marginal distribution of pnl_r is preserved almost exactly. The permuted PFs therefore cluster around the observed PF, and the resulting p-value clusters around 0.5.

Empirical evidence from the 7 cycle-4B pairs confirms this:

| Pair | Observed PF | MCPT p_pf |
|---|---|---|
| TSM-EURUSD | 1.231 | 0.398 |
| TSM-GBPUSD | 1.032 | 0.480 |
| TSM-USATECHIDXUSD | 1.086 | 0.514 |
| DON-EURUSD | 0.782 | 0.382 |
| DON-GBPUSD | 0.799 | 0.490 |
| DON-USATECHIDXUSD | 1.070 | 0.506 |
| **RSI2-USATECHIDXUSD** | **2.507** | **0.610** |

All 7 p-values cluster around 0.5 regardless of strategy quality. A PF 2.5 strategy and a PF 0.78 strategy both receive p ≈ 0.5. This gate cannot discriminate at the α = 0.00714 threshold with the available sample sizes (~100 trades per pair).

## 3. The scheme that WOULD work

The correct MCPT scheme for edge testing is `signal_time` (Bailey, Borwein, Lopez de Prado): permute entry timestamps and re-run the engine against each permuted timestamp set, then compare the observed PF to the null distribution of PFs under random entries.

That scheme is explicitly DEFERRED in `src/v17/validation/mcpt_runner.py` per rulings R-02 and R-05 (2026-11-04 audit): the stub `permute_signal_time` only relabels `ts_entry_ns` without re-running the engine, so `pnl_r` never changes and the null collapses to the observed value. The runner raises `NotImplementedError` to prevent silent no-op gates.

Building a correct `signal_time` scheme requires either: (a) a signal-time permutation harness that walks the engine per permutation (expensive — 500 × engine run on D1 is a few minutes per pair), or (b) a cross-sectional-return bootstrap that preserves calendar-time factor structure but shuffles the selection. Neither is in scope for cycle 4B.

## 4. Decision — RSI2-NAS100 advances as "gate-limited"

RSI2-USATECHIDXUSD is marked **GATE-LIMITED ADVANCE** and proceeds to C4B-S7 sealed-holdout evaluation on 2025-01-01 → 2026-10-18. Gate-limited means:

- Four of five secondary gates cleanly PASS (G1 PF 2.507, G2 trades 106, G4 R² 0.966, G5 stress PF 2.507 under 2× slippage).
- G3 fails by a single marginally-negative fold (fold 1: -2.9 R out of 7 folds totaling +78.9 R).
- MCPT fails with p_pf = 0.610, but the gate itself is structurally unable to reject at α = 0.00714 for any strategy under this scheme.
- The remaining 6 pairs all fail G1 outright AND MCPT. They SHELVE normally. No deviation needed for them.

The "gate-limited" tag means the pair is proceeding **DESPITE** a failed pre-reg gate, not with permission from one.

## 5. Holdout requirements (binding)

For RSI2-USATECHIDXUSD to convert from "gate-limited advance" to DEPLOY:

1. Sealed-holdout window `2025-01-01` → `2026-10-18` on D1 bars at `data/bars_d1/USATECHIDXUSD/holdout/`.
2. Strict rules: no parameter changes from the C4B-S5 commit (`1465ef3`).
3. Holdout PF ≥ 1.3 required.
4. Holdout WR ≥ 50% required (sanity check against the Connors 70-75% base rate).
5. Maximum drawdown (R) < 10R required.
6. FTMO circuit breakers: `ORBRiskEngine(10_000)` with 3% daily soft / 8% total hard. No hard-freeze trigger allowed.
7. **Scheme-1 MCPT rebuild NOT required for this verdict step** — it is a separate follow-up task and is required before any live-money commitment.

If all 6 hold: status is **HOLDOUT-PASS, PRE-LIVE**, still NOT DEPLOY. Live money is barred until scheme-1 MCPT is built and RSI2-NAS100 is re-tested through it with p_pf < 0.05 (single-pair, no Bonferroni).

If any one fails: **SHELVE** permanently. No further rescue tests.

## 6. What this means for your FTMO plan

- Holdout pass is NECESSARY but NOT SUFFICIENT for an FTMO attempt.
- Scheme-1 MCPT is the final gate before paying the FTMO fee.
- If scheme-1 MCPT also passes, 90-day demo run follows per your discipline commitments (user_trading_goals memory file).
- Only after demo pass does the first paid FTMO challenge get attempted.

## 7. Signed, in writing

This deviation is a conscious engineering call. User approved it via Path B in session 2026-11-11 after explicit briefing on p-hacking risk (see `2026-11-11-cycle4b-correction-prereg.md` § 1) and MCPT weakness. The combined risk-stack is:

- Dev PF 2.507 is upper bound (p-hack from cycle-4 → cycle-4B correction).
- G3 single-fold negative is weak evidence against persistence.
- MCPT bypass means no statistical rejection of null under the strongest available test.

Compound honest prior on RSI2-NAS100 surviving holdout AND scheme-1 MCPT AND 90-day demo AND FTMO Phase 1: **5-10%**. Still the highest-prior candidate produced in 4 cycles. Still an unlikely path.

Future-you must not trim this disclosure when quoting the cycle status. Remove it and the next commit builds a lie.
