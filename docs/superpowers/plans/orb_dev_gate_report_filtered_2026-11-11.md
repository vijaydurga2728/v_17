# ORB-NAS100 Dev Gate Report — 2026-11-11

**Trades (dev, 7-fold OOS):** 1093
**PF:** 1.2041  (G1 ≥ 1.3: FAIL)
**Trade count:** 1093  (G2 ≥ 25 relaxed floor: PASS)
**All folds net-positive:** NO  (G3: FAIL)
**R²:** 0.8735  (G4 ≥ 0.80: PASS)
**Cost-stress PF (2x slippage):** 1.450  (G5 ≥ 1.1: PASS)

### Per-fold pnl_r sum
| Fold | PnL (R) |
|---|---|
| 1 | 54.934 |
| 2 | -11.214 |
| 3 | 19.814 |
| 4 | 53.795 |
| 5 | -8.345 |
| 6 | 12.974 |
| 7 | 38.602 |

### Verdict: SHELVE

Decision rule: must pass all of G1-G5 to advance to dev MCPT (Task 15).
Honest-expectation base rate for reaching this point green: 20-35%.