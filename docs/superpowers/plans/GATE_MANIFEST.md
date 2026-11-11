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

- Status: IN-PROGRESS
- Spec: `docs/superpowers/specs/2026-11-11-orb-reversal-indices-design.md`
- Plan: `docs/superpowers/plans/2026-11-11-orb-reversal-indices.md`
- Engines: ORB-NAS100 (SP500 dropped 2026-11-11; no bars for `USA500IDXUSD`)
- Branch: `orb-reversal-indices`
- Prior cycle: SB 6-engine SHELVED 2026-11-10
- α: 0.05 (single engine; no Bonferroni)
