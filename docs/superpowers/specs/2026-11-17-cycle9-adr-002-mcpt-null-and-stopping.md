# ADR 002 — Cycle 9 MCPT: session-aligned null, fixed-count p-value, RSI2 correlation report

**ADR id:** cycle9-adr-002
**Status:** ACCEPTED (rev 2) — 2026-11-17, user review of Phase 3 rev 2 bundle. Corrections I, J, K, L accepted.
**Date-drafted:** 2026-11-17 (rev 1); revised 2026-11-17 (rev 2) after Phase 3 review.
**Decisions authorized in:** grilling rounds 1-2, 2026-11-17 (Q3, Q5, Q6). Q4 (sequential stopping)
was withdrawn in rev 2 — see Correction J.
**Supersedes-parts-of:** ADR 001 Correction A step 4 (block construction) and step 6 (log fields);
pre-reg §12 Tier 4 MCPT methodology. ADR 001 A.1 (100,000 permutations) and A.2 (plus-one p-value)
are **retained unchanged**.

### Revision history

- **rev 1:** Corrections I, J (Besag-Clifford sequential stopping, h=50, cap 100,000), K, L.
- **rev 2:** Phase 3 review rejected J. J now restores ADR 001's fixed-count procedure. K is updated
  to match. I and L are unchanged; I is still under separate review. See Appendix A for the
  calibration evidence on the rev 1 rule.
**Base commit:** `6d99a4c` on `cycle9-smc-liquidity`.

Read order becomes: pre-reg §1-15 → ADR 001 → this ADR. Where this ADR conflicts with ADR 001, this ADR wins.

## Correction I — Session-aligned block bootstrap (replaces ADR 001 A.4 block construction)

**Problem.** ADR 001 A.4 draws block starts uniformly over any bar index. Blocks then straddle session
boundaries, so a synthetic 09:30 bar can carry a 14:00 return. Sweep timing, ATR and the confirmation
window all depend on the intraday volatility profile, so the null is biased. Block size 25 vs 26 was also
unresolved (consistency audit §5 item 1).

**Resolution.**

1. **Session pool.** Let `S = [s_1 .. s_K]` be the dev full-RTH sessions in date order (half-days already
   excluded, ADR 001 G). Each session `s_k` holds its valid tradable M15 bars (the 25 bins `[09:30, 15:45)`
   minus any bin dropped by the `n_m1_bars < 5` rule, pre-reg §6). Sessions are used at their actual length;
   no session is padded or discarded for missing bins.
2. **Session return vector.** For `k >= 2`, with `mc` the mid close:
   - `g_k = log(mc[first bar of s_k]) − log(mc[last bar of s_{k-1}])` — overnight gap return.
   - `r_k[i] = log(mc[bar i of s_k]) − log(mc[bar i-1 of s_k])` for each later bar in `s_k`.
   - Block `B_k = (g_k, r_k[...])`. Length = bars in `s_k`. Full sessions give 25 returns (1 gap + 24
     intraday). This resolves the 25-vs-26 question.
   - `s_1` has no prior session and is not in the pool.
3. **Draw.** Per permutation, draw `K − 1` blocks uniformly **with replacement** from `{B_2 .. B_K}`.
4. **Calendar.** The synthetic path keeps the real dev calendar. Synthetic session `k` (for `k >= 2`) is
   labelled with real date `s_k` and holds the bars of drawn block `B_{π(k)}`, timestamped with the source
   block's NY-local bin times. Session `s_1` is copied unchanged as the anchor. Half-day exclusion, day
   count and PDH/PDL day-ordering are therefore unchanged.
5. **Rebuild mid-close.** Chain returns from the anchor: first synthetic close
   `= mc[last bar of s_1] · exp(g)`, then multiply by `exp(r)` bar by bar.
6. **Rebuild OHLC bid/ask by source-bar geometry.** For synthetic bar `b` sourced from real bar `src(b)`:
   `x_syn[b] = x_real[src(b)] − mid_c[src(b)] + mc_perm[b]` for every field `x` in
   `bid_o/h/l/c, ask_o/h/l/c, mid_o/h/l/c`. Spread and intrabar shape travel with the return that produced
   them (ADR 001 used geometry from the bar at the same position, which no longer matches after reordering).
7. **Unchanged from ADR 001 A.4:** recompute PDH/PDL (pre-reg §7) and ATR (ADR 001 E, fresh warmup on the
   synthetic stream), rerun the full strategy, record synthetic `mean_r`. A permutation with zero synthetic
   trades records `mean_r = 0` and counts as not exceeding a positive observed `mean_r`.

**Limitation of this null (must be stated with every Tier 2-4 result).** Sessions are resampled
independently. The null preserves within-session return structure, the overnight gap attached to each
session, and source-bar geometry. It does **not** preserve multi-session serial dependence or regime
persistence (volatility clustering across days, multi-day trends). A p-value from this MCPT answers:
"is the strategy's mean R unusual relative to paths built from independently shuffled real sessions?"
Results must be interpreted conditionally on that null.

## Correction J (rev 2) — Fixed-count p-value, no early stopping

**Supersedes:** rev 1 Correction J. **Restores:** ADR 001 A.1 and A.2 unchanged.

- Every slot that reaches Tier 2 runs **exactly 100,000 permutations**. No early stopping.
- **`p = (count(null_mean_r >= observed_mean_r) + 1) / (100_000 + 1)`.** Minimum p ≈ 9.9999e-6.
- Tier 2 (p ≤ 0.05) and Tier 3 (p ≤ 0.0003787879) thresholds are unchanged. Do not relax.
- Seeds: ADR 001 A.3 per-slot seed. Permutation `j` of a slot uses
  `numpy.random.default_rng([slot_seed, j])`.
- Logging (ADR 001 A.6): one row per permutation (`perm`, `seed`, `blocks_hash`, `n_trades_null`,
  `mean_r_null`) to `out/c9/mcpt_perms_<slot_id>.parquet`. `out/c9/mcpt_report.csv` records
  `n_perms` (always 100,000), `exceedances`, `p_value` and `observed_mean_r`.
- **Compute (measured 2026-11-17, synthetic data shaped like dev, project venv):** 6.2 ms per
  permutation with numba 0.67.0 (≈ 10 min per slot) and 56.5 ms in pure Python (≈ 1.6 h per slot).
  Reproduce with `scripts/bench_c9_mcpt.py`. Compute no longer motivates sequential stopping.

## Correction K — Tier 4 holdout MCPT uses the same method

**Supersedes:** pre-reg §12 Tier 4 "scheme-1 same methodology, holdout-only block bootstrap".

- Holdout MCPT uses Correction I and Correction J (rev 2: fixed 100,000 permutations, plus-one p)
  on the holdout session pool only (no dev sessions in the pool).
- Holdout per-slot seed: `20261116 * 1_000 + 500 + slot_index`.
- Threshold unchanged: p ≤ 0.05. Holdout still touched exactly once per slot.

## Correction L — RSI2-NAS100 overlap report (reporting only, NOT a gate)

For every slot **accepted** under pre-reg §12 (Tier 1-4 baseline + Tier 4 at +1pt), report on dev and holdout
separately:

1. Pearson and Spearman correlation between the cycle 9 slot's daily R (sum of trade R by NY exit date, 0 on
   no-trade days) and RSI2-NAS100's daily mark-to-market R. RSI2 daily R is
   `(close_t − close_{t−1}) / r_dist` while a position is open, else 0, using the `rsi2_runner` trade list.
2. Share of cycle 9 trade days on which an RSI2 position was open, split by cycle 9 direction.
3. Worst 20-day rolling combined R drawdown of the two streams at equal 1R weight.

These numbers inform ensemble sizing only. They do not change any slot's pass/fail status.

## Unchanged

Grid (12 slots), Tier 1 gates, Bonferroni denominator 132 (ADR 001 H), Tier 5 slippage, all of pre-reg §10
as corrected by ADR 001.

## Execution boundary

- On ACCEPTED: commit this ADR, then Phase 3 code start requires its own explicit user authorization.
- Do not run backtests, touch holdout, or modify cycle 4B strategy code.

## Appendix A — Calibration of the withdrawn rev 1 rule (for the record)

The Phase 3 review rejected rev 1 J because, with the true exceedance probability at exactly
q = 0.05, the rule `p = 50/m` reports p ≤ 0.05 about 48% of the time. A simulation on 2026-11-17
(`scripts/c9_mcpt_calibration.py`; 200,000 null replications; seed 20261117) confirms that number,
and compares it with the fixed-count rule that rev 2 restores:

| Quantity | Sequential `h/m` (rev 1) | Fixed 100k `(e+1)/(N+1)` (rev 2) | Nominal |
|---|---|---|---|
| Type-I error at α = 0.05 (observed drawn from the null, q ~ U(0,1)) | 0.0504 | 0.0503 | 0.05 |
| Type-I error at α = 0.01 | 0.0099 | 0.0100 | 0.01 |
| Type-I error at α = 0.0003788 | 0.00040 | 0.00040 | 0.00038 |
| P(p ≤ 0.05) when q is exactly 0.05 | 0.482 | 0.492 | — |

Reading: the ~48% figure is the conditional pass rate exactly at the boundary. Any Monte Carlo
p-value has it, including the fixed-count rule (49%). It is not the type-I error rate, which is
nominal for both rules **in this simulation**. Scope: the simulation assumes the ideal continuous,
exchangeable null (the observed statistic's true tail probability q ~ Uniform(0,1)). It is
calibration evidence under that assumption, not a general proof for every bootstrap null model;
ties and discreteness in `mean_r` (e.g. many zero-trade permutations) make either rule conservative,
not anti-conservative, because ties count as exceedances. Rev 2 restores the fixed-count rule anyway: it was the pre-approved ADR 001
procedure, the measured compute (≈ 10 min per slot) removes the reason for stopping early, and it
leaves nothing to dispute. This appendix exists so a future cycle does not reject a valid
sequential procedure for the wrong reason, or adopt one without this check.
