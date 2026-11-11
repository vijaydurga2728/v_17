# ORB Trend-Filter Pre-Registration — 2026-11-11

**Status:** LOCKED before running. No parameter tuning after.

## Hypothesis

ORB-Reversal loses in strong directional-trend years (2019 bull, 2022 bear)
because fade logic sells trend. A simple daily-trend regime filter that
blocks counter-trend fades should lift PF and eliminate the two negative
fold-years.

## Filter definition

Compute a daily series `ema20_d1` = 20-day exponential moving average of
daily close (resampled from M1 to D1 via pandas `.resample("1D")`).

For each NY date D with session close `c = close_d1[D - 1 trading day]`
and `e = ema20_d1[D - 1 trading day]`:

- `regime(D) = "bull"` when `c > e * 1.03`
- `regime(D) = "bear"` when `c < e * 0.97`
- `regime(D) = "neutral"` otherwise

Filter rule applied at FSM signal emit:
- `regime == "bull"` and `side == "short"` → drop signal (do not enter)
- `regime == "bear"` and `side == "long"` → drop signal (do not enter)
- all other combinations → enter as before

## Parameters (frozen)

- EMA period: 20 (days).
- Bull threshold: +3.00%.
- Bear threshold: -3.00%.
- Lookback uses prior-day close only (no same-day lookahead).

No grid search. No optimizer. These numbers come from standard trend-regime
practice; they are fixed before the run.

## Acceptance rule (one shot)

Advance to MCPT only if ALL of:
1. G1 PF ≥ 1.3.
2. G2 trade_count ≥ 25 (same relaxed floor).
3. G3 every fold (2018-2024) net-positive.
4. G4 R^2 ≥ 0.80.
5. G5 cost-stress PF ≥ 1.1.

Any one fail → **SHELVE** and stop. No second filter attempt. No parameter
re-tune. Strategy moves to the "shelved" column of the cycle manifest.

## Risk disclosure

This is ONE degree of data-dredging. Theory-grounded, one-shot, pre-registered
threshold. Still raises posterior false-discovery probability versus a zero-
filter test. Honest per-engine pass probability conditional on fold-pattern
evidence: 25-40% (up from 20-35% unconditional).

If this filter PASSES, MCPT α remains 0.05. No Bonferroni across filter
variants (there is only one variant tested).

If this filter FAILS, the ORB-Reversal cycle ends. Next cycle candidates
listed in GATE_MANIFEST.
