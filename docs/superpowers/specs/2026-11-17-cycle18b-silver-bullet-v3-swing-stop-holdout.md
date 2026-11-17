# Cycle 18b — Silver Bullet v3 with swing stop, one shot on the untouched holdout (pre-registration)

**Status:** FROZEN 2026-11-17. User "yes to all": Q1 = stop rule **A** (chosen by the user), Q2 = one shot on 2025 → today,
Q3 = close Silver Bullet if it fails. Committed before any v3-A code or result.

## Change vs cycle 18 (only this)
**Stop A — beyond the window's swing:** long SL = lowest mid low of the bars from window start through FVG candle 1
(inclusive), minus buffer_min; short SL = highest mid high of those bars plus buffer_min. Distance below buffer_min →
buffer_min. Everything else exactly as cycle 18 (`2026-11-17-cycle18-silver-bullet-ict-original-prereg.md`).

## Exam (one shot)
- Data: NY dates **2025-01-01 → end of data** only. Not run on 2018-2024 (those results were already seen; the stop
  rule must be judged on unseen data).
- 12 slots as cycle 18. **Pass (any slot):** PF ≥ 1.3 and luck test p ≤ 0.05/12 (cycle 17/18 random-entry null,
  5,000 permutations, seed `20261117*1000 + 1200 + slot_index`).
- Order of work (feedback rule): code + unit tests → independent re-implementation must match trade by trade on
  NY AM NAS100 and EURUSD → hand-check table → results.
- **Outcome:** no slot passes → Silver Bullet closed for good.
