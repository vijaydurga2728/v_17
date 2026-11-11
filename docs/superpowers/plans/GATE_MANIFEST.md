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
