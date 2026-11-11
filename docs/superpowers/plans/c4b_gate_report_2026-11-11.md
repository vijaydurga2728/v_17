# Cycle 4B Formal Gate Report — 2026-11-11

- Bonferroni alpha (7 pairs): **0.00714**
- MCPT permutations: 500, scheme pnl_bootstrap, block_size 5
- G2 relaxed-floor: 25 trades

| Engine | Trades | PF | R² | Stress PF | G1 | G2 | G3 | G4 | G5 | MCPT p_pf | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| TSM-EURUSD | 104 | 1.231 | 0.692 | 1.231 | F | P | F | F | P | 0.3980 | **SHELVE** |
| TSM-GBPUSD | 104 | 1.032 | 0.056 | 1.032 | F | P | F | F | F | 0.4800 | **SHELVE** |
| TSM-USATECHIDXUSD | 104 | 1.086 | 0.209 | 1.084 | F | P | F | F | F | 0.5140 | **SHELVE** |
| DON-EURUSD | 88 | 0.782 | 0.484 | 0.782 | F | P | F | F | F | 0.3820 | **SHELVE** |
| DON-GBPUSD | 86 | 0.799 | 0.600 | 0.799 | F | P | F | F | F | 0.4900 | **SHELVE** |
| DON-USATECHIDXUSD | 90 | 1.070 | 0.320 | 1.068 | F | P | F | F | F | 0.5060 | **SHELVE** |
| RSI2-USATECHIDXUSD | 106 | 2.507 | 0.966 | 2.507 | P | P | F | P | P | 0.6100 | **SHELVE** |

### Pairs advancing to holdout: NONE