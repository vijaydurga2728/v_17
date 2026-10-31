# ADR-0003: Anchored Walk-Forward, 12 Folds, IS/OOS 60/40

## Status
Accepted

## Date
2026-10-28

## Context
The validation gate (M6, SPEC §6.2) must demonstrate that the ICT setups generalize across market regimes before any live or demo `order_send` fires. A single IS/OOS split is insufficient: it tests one slice of history. Robert Pardo's walk-forward methodology (The Evaluation and Optimization of Trading Strategies, 2008) is the standard technique for repeatedly re-testing a strategy over rolling or anchored windows and measuring how often the OOS result is consistent with the IS result.

Available data: ~12 years of 1-minute Dukascopy bars for EURUSD + GBPUSD (2014–2026).

Our setups have **no tunable parameters** at the strategy level — the ICT rules are fixed by SPEC §5 glossary. Walk-forward here is not for parameter optimization; it is for **regime-robustness verification**: show that the fixed rules produce an edge in every era, not only in-sample.

## Decision
Run **anchored walk-forward with 12 folds** on each symbol:

- IS window grows: fold `k` uses `[t0, t0 + k * step]` as IS.
- OOS window: the next `step` of data after IS, where `OOS = 40%` of fold total and `IS = 60%`.
- Step = (dataset_length − initial_IS) / 12.
- No parameter tuning on IS. IS exists so that the operator can inspect per-fold IS vs OOS alignment; strategy constants stay fixed across folds.
- Pass criterion feeds into gate: ≥ 4 of 12 OOS folds individually pass the full §6.2 thresholds (PF ≥ 1.8, Sharpe ≥ 2.0, Max DD < 6%, winrate ≥ 50%, trades ≥ a per-fold floor).

## Alternatives Considered

### Rolling (non-anchored) walk-forward
- **Pros**: Each IS window has fixed length, closer to "how a trader actually re-evaluates".
- **Cons**: Discards older history entirely; loses signal that the setups also worked under 2014–2018 regimes; worse for strategies with fixed rules (nothing is being re-fit).
- **Rejected**: anchored keeps the full history visible and is the honest choice for fixed-rule strategies.

### Fewer folds (3–6)
- **Pros**: Larger OOS windows, more trades per fold.
- **Cons**: Weaker statistical power on consistency across time. A strategy can pass 2 of 3 folds and still be a coin flip.
- **Rejected**: 12 folds give enough resolution to see regime failures (2015 CHF shock, 2016 Brexit, 2020 COVID, 2022 rate hikes).

### More folds (24+)
- **Pros**: Finer temporal resolution.
- **Cons**: OOS window per fold shrinks to months, dropping below the ≥ 200 OOS trade floor; makes per-fold metrics unreliable (small-sample noise).
- **Rejected**: 12 is the sweet spot between resolution and per-fold statistical power given our expected trade frequency (~1–3 trades/day/pair).

### Single IS/OOS split (70/30 or 60/40, no folds)
- **Pros**: Simplest.
- **Cons**: Tests exactly one slice; vulnerable to lucky-era bias.
- **Rejected**: insufficient evidence for live deployment of real money.

### Combinatorial purged cross-validation (López de Prado)
- **Pros**: Addresses leakage in ML contexts.
- **Cons**: Designed for feature-engineered classifiers; overkill for a deterministic rule system with no learned parameters.
- **Rejected**: wrong tool for a non-ML strategy.

## Consequences
- The validation gate requires 12 full backtest runs per symbol per release; CI budget absorbs this (≤ 15 min total per SPEC §6.6).
- Per-fold metrics (`walkforward.json`) are first-class artifacts; the daily report highlights which folds pass and which fail.
- Any rule change in M2/M3 forces a full re-run; this is intended — rule changes must earn their pass through evidence.
- If fewer than 4 of 12 OOS folds pass, the gate fails and live stays locked. There is no partial credit.
