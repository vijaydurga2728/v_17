# ADR-0004: Hybrid Monte Carlo — 500 Trade-Order Permutations + 500 Block-Bootstrap (block = 5)

## Status
Accepted

## Date
2026-10-28

## Context
Walk-forward (ADR-0003) measures regime consistency over time. It does not answer: given this strategy's trade distribution, how extreme could the drawdown realistically be under a different ordering of the same trades?

Monte Carlo on the realized trade P&L sequence is the standard answer. The method must honestly reflect two realities:

1. **Order variance.** A win-heavy start masks drawdown; a loss-heavy start reveals it. We need the distribution of possible orderings.
2. **Streak clustering.** ICT setups cluster losses around the same adverse regime (e.g., a non-trending week kills Judas sweeps). An IID shuffle destroys this clustering and understates the real worst-case drawdown.

The validation gate (SPEC §6.2) uses MC percentiles to set the FTMO drawdown buffer:

- MC 5th-percentile PF ≥ 1.3.
- MC 95th-percentile Max DD ≤ 8% (FTMO 10% − 2% buffer).

## Decision
Run **1 000 Monte Carlo simulations per OOS trade set, split into two methods**:

- **500 trade-order permutations.** Shuffle the realized P&L vector uniformly, replay, compute metrics. Captures order variance.
- **500 block-bootstrap resamples with block size 5.** Resample contiguous blocks of 5 trades with replacement to reconstruct a trade series of the same length, replay, compute metrics. Preserves local loss-streak clustering.

The two populations are combined into a single distribution of 1 000 outcomes. Percentiles (5th, 50th, 95th) and the pass flags feed into the validation gate.

Seeded via `BacktestConfig.seed`; reproducible across runs.

## Alternatives Considered

### IID bootstrap only (sample individual trades with replacement)
- **Pros**: Simple and standard.
- **Cons**: Destroys loss-streak clustering → systematically underestimates max drawdown → false sense of safety against FTMO's hard 10% rule.
- **Rejected**: understates drawdown risk, which is exactly the risk FTMO fails accounts on.

### Pure permutation only (no bootstrap)
- **Pros**: Preserves the exact trade distribution.
- **Cons**: Does not generate "unseen" sequences; variance comes only from ordering. Misses the question "what if we got the same kind of loss cluster twice".
- **Rejected**: narrower than needed.

### Synthetic price generation via GBM / jump-diffusion
- **Pros**: Decouples strategy from historical path dependence.
- **Cons**: Introduces a new model (GBM) with its own calibration + assumption risk; invalid for FX microstructure during news; evaluates the simulator more than the strategy.
- **Rejected**: adds assumption risk without closing the gap we care about.

### Parametric Monte Carlo (fit a distribution to trade returns, sample)
- **Pros**: Compact, fast.
- **Cons**: Picks a distribution (normal, t, mixture) and inherits its tail assumptions; ICT trade returns are fat-tailed and skew-heavy; parametric fits lie about tail risk.
- **Rejected**: tail misrepresentation on the one thing FTMO cares about.

### Block-bootstrap only
- **Pros**: Preserves streak clustering.
- **Cons**: Reduces variance in ordering patterns relative to full permutation; percentiles narrower than hybrid.
- **Rejected**: hybrid gives both signals; cost is negligible (1 000 simulations is fast).

## Consequences
- The MC component ships as deterministic given a seed, so CI can regression-test MC percentiles.
- Block size 5 is a tunable; locked at 5 by this ADR. Any change requires a new ADR because it influences the drawdown bound that unlocks live trading.
- `montecarlo.json` is a first-class artifact per run; the daily report plots the MC equity-curve envelope.
- Combining two methods into one population is a deliberate choice: percentiles reflect a mix of order-variance and streak-variance evidence.
