# ORB-NAS100 Dev Gate Report — 2026-11-11

**Trades (dev, 7-fold OOS):** 1215
**PF:** 1.1422  (G1 ≥ 1.3: FAIL)
**Trade count:** 1215  (G2 ≥ 25 relaxed floor: PASS)
**All folds net-positive:** NO  (G3: FAIL)
**R²:** 0.7886  (G4 ≥ 0.80: FAIL)
**Cost-stress PF (2x slippage):** 1.370  (G5 ≥ 1.1: PASS)

### Per-fold pnl_r sum
| Fold | PnL (R) |
|---|---|
| 1 | 49.689 |
| 2 | -13.683 |
| 3 | 4.022 |
| 4 | 52.879 |
| 5 | -13.820 |
| 6 | 15.352 |
| 7 | 31.213 |

### Verdict: SHELVE

Decision rule: must pass all of G1-G5 to advance to dev MCPT (Task 15).
Honest-expectation base rate for reaching this point green: 20-35%.