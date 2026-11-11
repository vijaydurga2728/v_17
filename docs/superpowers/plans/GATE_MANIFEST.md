# Silver Bullet 6-Engine Gate Manifest

**Status 2026-11-10: CYCLE SHELVED.** Per spec §13.2 and user decision 2026-11-10.

Per-engine summary (dev data only, no MCPT gate run completed):

| Engine | Trades | Exits (TP/SL/TIME) | PF | Win Rate | pnl_r sum | Verdict |
|---|---|---|---|---|---|---|
| SB-LDN-CE | 25 | 2/17/6 | 0.67 | 32.0% | -5.66 | FAIL (sampled, pre-MCPT) |
| SB-LDN-AG | pending | - | - | - | - | SHELVED |
| SB-NYAM-CE | pending | - | - | - | - | SHELVED |
| SB-NYAM-AG | pending | - | - | - | - | SHELVED |
| SB-NYPM-CE | pending | - | - | - | - | SHELVED |
| SB-NYPM-AG | pending | - | - | - | - | SHELVED |

Portfolio-layer MCPT (α=0.05): NOT RUN.

**System verdict: SHELVE.**

Reason: SB-LDN-CE (1 of 6 engines, dev 2018-2024) produced 25 trades over 7 years (~0.3/month), PF 0.67, Win Rate 32%, only 2/25 TPs reached. G1/G2/G3/G4 pre-fail without running MCPT. The frozen Silver Bullet rulebook does not produce enough trades or enough winners on this data. Spec §17 honest-expectation range (5-15% end-to-end success) landed at the low end for this one engine; remaining 5 engines estimated unlikely to materially differ (base rate 10-15% per engine). User-approved shelve rather than burn ~8-10h compute confirming the verdict.

No live money committed. No FTMO fee paid. Cycle cost: engineering time only.

**Next cycle: ORB reversal on indices** — new spec, new gate, 2-3 week build. Reuses 70% of infrastructure. Details in `.superpowers/sdd/2026-11-03-silver-bullet-6-engine-doctrine-test/orb-cycle-handoff.md`.

---

## ORB Reversal Indices (2026-11-11)

- Status: **SHELVED 2026-11-11** at dev secondary gates (Task 14).
- Spec: `docs/superpowers/specs/2026-11-11-orb-reversal-indices-design.md`
- Plan: `docs/superpowers/plans/2026-11-11-orb-reversal-indices.md`
- Gate report: `docs/superpowers/plans/orb_dev_gate_report_2026-11-11.md`
- Engines: ORB-NAS100 (SP500 dropped 2026-11-11; no bars for `USA500IDXUSD`)
- Branch: `orb-reversal-indices`
- Prior cycle: SB 6-engine SHELVED 2026-11-10
- α: 0.05 (single engine; no Bonferroni)

### Dev gate summary (ORB-NAS100, 2018-2024 OOS, 7 folds, mid-price)

| Gate | Metric | Threshold | Value | Verdict |
|---|---|---|---|---|
| G1 | PF | >= 1.3 | 1.142 | **FAIL** |
| G2 | trades | >= 25 (ORB relaxed) | 1215 | PASS |
| G3 | all folds net-positive | all > 0 | folds 2 & 5 negative | **FAIL** |
| G4 | R^2 (equity curve vs time) | >= 0.80 | 0.789 | **FAIL** (borderline) |
| G5 | cost-stress PF (2x slippage) | >= 1.1 | 1.370 | PASS |

Additional metrics: Sharpe 0.71, max_dd 53R, win_rate 16.8%, avg_r 0.10.

**System verdict: SHELVE.** 3 of 5 gates fail; not borderline. No MCPT or
holdout run per plan decision rule (SHELVE at dev gate if fail).

Reason: The naive ORB-Reversal rulebook fades every 30-min-OR breakout on
NAS100 M1 and loses on expectancy. The strategy is too frequent (1215
trades / 7 years ≈ 170/year, far above handoff's 20-60 estimate), the
win_rate (16.8%) is well below the 0.5R target's break-even (~67%), and
the equity curve shows two losing fold-years out of seven.

### Pre-registered trend-filter rescue test (one shot, 2026-11-11)

Pre-reg: `docs/superpowers/plans/orb_trend_filter_prereg_2026-11-11.md`.
Filter: D1 EMA_20 ±3% regime; bull drops short-fade, bear drops long-fade.

| Gate | No filter | + Trend filter | Threshold |
|---|---|---|---|
| G1 PF | 1.142 FAIL | 1.204 FAIL | ≥ 1.3 |
| G2 trades | 1215 PASS | 1093 PASS | ≥ 25 |
| G3 all folds + | FAIL | FAIL | all > 0 |
| G4 R² | 0.789 FAIL | 0.874 PASS | ≥ 0.80 |
| G5 stress PF | 1.370 PASS | 1.450 PASS | ≥ 1.1 |

Filter moved the needle in the predicted direction (fold 2: -13.7 → -11.2,
fold 5: -13.8 → -8.3, Sharpe 0.71 → 0.995, R² passes) but missed G1 and
G3. Hypothesis directionally validated, magnitude insufficient.

**Final verdict: SHELVE.** Pre-reg rule honored — no second filter attempt.

No live money committed. No FTMO fee paid. Cycle cost: engineering time
only.

**Next cycle candidates** (from handoff line 104): VWAP mean reversion
(archetype 2), session liquidity scalping (archetype 3), DXY-FX
intermarket (archetype 4), overnight gap fade (archetype 5).

---

## Overnight Gap Fade (2026-11-11, cycle 3)

- Status: **SHELVED 2026-11-11** at dev secondary gates.
- Spec: `docs/superpowers/specs/2026-11-11-overnight-gap-fade-design.md`
- Gate report: `docs/superpowers/plans/gap_dev_gate_report_2026-11-11.md`
- Engine: GAP-NAS100 (`USATECHIDXUSD`)
- Branch: `orb-reversal-indices` (same branch; gap-fade work stacked)

### Dev gate summary (GAP-NAS100, 2018-2024 OOS, 7 folds)

| Gate | Metric | Threshold | Value | Verdict |
|---|---|---|---|---|
| G1 | PF | >= 1.3 | **0.936** | FAIL |
| G2 | trades | >= 25 | 849 | PASS |
| G3 | all folds net-positive | all > 0 | 5 of 7 negative | FAIL |
| G4 | R^2 | >= 0.80 | 0.194 | FAIL |
| G5 | cost-stress PF (2x slippage) | >= 1.1 | 0.913 | FAIL |

Additional: win_rate 62.9% (matches published base rate ~70%), avg_r -0.021,
max_dd 22.9R, Sharpe -0.49.

**Verdict: SHELVE.** Four of five gates fail. Not borderline.

Reason: The gap-close signal is real (62.9% WR is close to published
70-75% base rate) but the asymmetric R/R of 1R-stop / 0.5R-target
requires >=66.7% WR to break even; we are 4 pp short. The two negative
expectancy fold-years (2018, 2019, 2020, 2022, 2024 all negative; 2021,
2023 positive) suggest the NAS100 overnight bias has strengthened
post-2020 — gap-ups continuing more often than closing. PF 0.94 is a
losing system.

Pre-reg explicitly forbids TP/SL ratio re-tune or filter stacking.
Honoring the pre-reg: SHELVE.

### Three-cycle session verdict (2026-11-11)

- SB 6-engine: SHELVED (one engine sampled, PF 0.67, 32% WR).
- ORB Reversal NAS100: SHELVED after naked and after trend-filter rescue
  (PF 1.14 -> 1.20 with filter, G1/G3 still fail).
- Overnight Gap Fade NAS100: SHELVED (PF 0.94, G1/G3/G4/G5 fail).

Three strategy archetypes evaluated against the same infra in one session:
mechanical fade (ORB), mean-reversion fade (Gap), structural doctrine (SB).
All fail on NAS100 M1 dev data with the user's risk discipline (0.5% /
trade, 1 trade/day, no overrides).

**Honest read:** NAS100 M1 may not be the right instrument for fade
systems in the 2018-2024 regime. Momentum-following archetypes or
multi-instrument diversification (FX, commodities, crypto) are
untested. User's "last try" fatigue signal is active.

**Strong recommendation:** stop coding. Take a 2-week break before
opening cycle 4. Infra is reusable for any next attempt.
