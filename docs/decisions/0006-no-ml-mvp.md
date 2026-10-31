# ADR-0006: No Machine Learning in MVP — Deterministic ICT Rules Only

## Status
Accepted

## Date
2026-10-28

## Context
The v17 MVP targets FTMO Challenge $100k. The validation gate (SPEC §6.2) requires passing walk-forward (ADR-0003) and hybrid Monte Carlo (ADR-0004) thresholds before live or demo order submission. The ICT setups (Silver Bullet, Judas Swing) are already fully specified by the glossary in SPEC §5 and the entry stack of FVG + MSS + OB + Liquidity Sweep.

ML approaches — classifiers that score setup quality, RL agents that learn entry/exit timing, or models that weight rule confluence — are commonly proposed to "boost" trading edge. Research (`docs/research/last30days.md`, `docs/research/deep-research.md`) found no public honest forward-tested ICT ML system. The operator has no ML pipeline, no labelled dataset, and no evaluation infrastructure for ML in this repo.

A trading system's job is to find and exploit an edge. If the deterministic ICT rules do not have an edge, ML cannot invent one from the same features; ML can only re-weight what the rules already see. If the rules do have an edge, ML adds overfit risk, opacity, and FTMO-explainability problems without clear upside.

## Decision
**No ML in the MVP.** M3 Setup Engines evaluate deterministic rules only. No supervised classifier, no RL, no learned confluence weights, no neural signal filter.

If and only if the deterministic system passes the validation gate on OOS data, future work may explore ML extensions. Each extension requires its own ADR (0010+), its own validation gate, and its own release train.

## Alternatives Considered

### Supervised classifier on setup features
- **Pros**: Could learn to filter weak setups; interpretable with SHAP; small enough to run locally.
- **Cons**: Requires labelled training data; introduces IS/OOS leakage risks; adds a dependency, a training pipeline, and a model drift surface; defers the gate.
- **Deferred**: future ADR after MVP ships and passes gate.

### Reinforcement learning agent for entry/exit timing
- **Pros**: Can learn exit management, trailing stops, partial-close logic.
- **Cons**: Sample inefficiency on daily-frequency setups; reward hacking; unstable training; opaque behavior under news events; incompatible with FTMO explainability.
- **Deferred**: future ADR after MVP ships.

### Learned rule-weight model (confluence weighting)
- **Pros**: Small model, interpretable.
- **Cons**: We only have ~1–3 setups/day/pair; dataset is too small to fit weights without overfitting; walk-forward would need per-fold re-fits that reintroduce curve-fit risk.
- **Deferred**: future ADR after MVP ships.

### Pre-trained foundation model (LLM / time-series transformer) as feature extractor
- **Pros**: Trendy; could extract regime features.
- **Cons**: Latency; API cost; non-deterministic without careful seeding; FTMO explainability nightmare; no evidence it beats the deterministic rules.
- **Deferred**: not planned.

## Consequences
- M3 Setup Engines stay small, pure, deterministic, and 100% unit testable (SPEC §7 M3).
- Validation gate interprets failure as "no edge in the rules" and halts the project honestly rather than papering over with ML.
- Build order (M1–M10) stays unchanged; no model-serving infrastructure needed.
- Future ML work is on-ramp, not retrofit: Signal objects already carry `confluence` state, which is a natural feature vector when ML is reconsidered.
