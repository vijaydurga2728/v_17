# ORB Reversal Indices — Design Spec

**Status:** FROZEN
**Date:** 2026-11-11
**Prior cycle:** Silver Bullet 6-engine — SHELVED 2026-11-10.
**Handoff source:** `C:\personal\v_17\.worktrees\sb-6-engine-gate\.superpowers\sdd\2026-11-03-silver-bullet-6-engine-doctrine-test\orb-cycle-handoff.md`
**Branch:** `orb-reversal-indices` (from `main` HEAD `dac47c1`).
**Plan:** `docs/superpowers/plans/2026-11-11-orb-reversal-indices.md`.

---

## 1. Global constraints

- Target branch: `orb-reversal-indices`.
- Instruments: `USATECHIDXUSD` only (SP500 downgrade 2026-11-11 — `USA500IDXUSD` bars absent in repo).
- Strategy: ORB Reversal — fade the opening-range breakout.
  - OR window: 09:30-10:00 ET (30 min).
  - Entry: STOP order at OR_high (short reversal) after breakout AND close back inside OR within 15 min; symmetric for OR_low (long).
  - Stop: breakout extreme ± 0.5 × ATR_14 (M1 ATR).
  - Target: 0.5R initial; trail to session VWAP when VWAP farther than 0.5R from entry.
  - Session window: 09:30-11:30 ET.
  - Max trades/day/instrument: 1 (FTMO consistency friendly).
- FTMO account: $10k Standard, 0.5% equity risk/trade.
- Circuit breakers: daily -3% soft stop, total -8% hard freeze.
- Walk-forward: 7-fold anchored over `2016-11-01` → `2024-12-31`.
- Sealed holdout: `2025-01-01` → `2026-10-18`.
- MCPT: scheme `pnl_bootstrap` only (R-02, R-05 carried over); block size 5; 500 permutations dev / 1000 holdout.
- Significance: α = 0.05 (single engine; no Bonferroni correction).
- Cost model: 0.5 pt market-order slippage USATECH; 0 on limit/stop fills; FTMO $0 commission on indices; bid/ask paired bars.

## 2. User-approved operating constraints

1. FTMO budget: 1-2 Standard challenge attempts (~$500-700 each = $500-1400).
2. Demo-first: 90 days free demo before any paid challenge.
3. No discretionary override: user commits to letting algo run without intervention.
4. Non-ICT: strategy does not use ICT mechanics.
5. Build timeline: 2-3 weeks to a gate verdict.
6. Ambition: FTMO Phase 1 pass → Phase 2 pass → funded → monthly payouts without blowing account. User accepts ~3-6% end-to-end base rate.

## 3. Pre-flight rulings carried over

- **R-02** (MCPT scheme 1 "signal_time" deferred): still applies.
- **R-05** (Scheme 1 code raises `NotImplementedError`): still applies.
- Audit 1 reclassification was SB-specific; ORB rulebook classified fresh from academic sources.

## 4. Honest expectation (ORB cycle, 1-engine NAS100-only)

- Gate pass probability (ORB-NAS100 passes MCPT + secondary gates): 20-35%.
- Passing engine survives holdout: 50%.
- Compound (DEPLOY status achieved): **10-18%**.
- From DEPLOY to FTMO funded + first payout: 30-50% multiplicative.
- **End-to-end (gate pass → demo → challenge → funded → first payout): 3-9%**.

SP500 downgrade removed the portfolio-diversification argument; probabilities per handoff lines 94-100 reduced accordingly (handoff's 8-18% DEPLOY assumed 2 engines).

## 5. Verdict destinations

- Dev gate report: `docs/superpowers/plans/orb_dev_gate_report_2026-11-11.md`.
- Dev MCPT report: `docs/superpowers/plans/orb_dev_mcpt_report_2026-11-11.md`.
- Holdout report: `docs/superpowers/plans/orb_holdout_report_2026-11-11.md`.
- Cycle status: `docs/superpowers/plans/GATE_MANIFEST.md`.
