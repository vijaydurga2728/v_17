# RSI2-USATECHIDXUSD Scheme-1 MCPT Report — 2026-11-11

**Required gate before live money** per `2026-11-11-cycle4b-mcpt-scheme-addendum.md`.
**Permutations:** 500. **Alpha (single pair):** 0.05.
**Null model:** random long-only entries uniformly sampled from eligible D1 bars in window.

## Dev window (2018-01-01 → 2025-01-01, 7 folds union)

- Observed PF: **2.507** over 106 trades.
- Null PF — median 1.607, mean 1.736, p95 2.986.
- **p_pf = 0.1140** (FAIL vs alpha 0.05).

## Holdout window (2025-01-01 → 2026-10-18)

- Observed PF: **4.895** over 29 trades.
- Null PF — median 2.013, mean 2.946, p95 8.463.
- **p_pf = 0.1480** (FAIL vs alpha 0.05).

## Combined verdict

- Dev pass: **False**. Holdout pass: **False**.
- Both required for live-money clearance.

### Status: SHELVE (both fail scheme-1)

## Honest interpretation

The null-model baseline reveals the uncomfortable truth: random long-only entries on NAS100 during 2018-2024 and 2025-2026 produce **positive PF (~1.6-2.0) without any signal**, because both windows are bull regimes with upward drift.

Signal uplift:
- Dev: 1.607 → 2.507 = +55% (good, but 11.4% of random beats it).
- Holdout: 2.013 → 4.895 = +143% (strong, but 14.8% of random beats it).

What this means in practice:

1. Passive long-only NAS100 during 2018-2026 would have made money; the RSI(2) entry rule captures *some* edge over passive, but not with p < 0.05 confidence given the sample sizes.
2. In a bear regime, the null PF would collapse below 1.0 and the RSI(2) uplift would need to carry the whole strategy. Untested.
3. The G1 PF ≥ 1.3 threshold was set assuming a neutral baseline. Against the actual bull-regime baseline PF ~1.7, the threshold should have been ~2.2 to represent "real edge". Observed PF 2.5 clears that but not with the statistical margin pre-reg demands.

No live-money commitment permitted under the current test.

Paths from here:
- Accept the shelve and start a new cycle with a drift-neutral signal (long/short pair, spread, volatility-regime filter).
- Add bear-regime data (2008, 2015-H2, Feb-Mar 2020 only partial) to widen the sample before retrying.
- Accept the shelve and stop.