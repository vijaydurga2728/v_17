# Cycle 23 verdict — SHELVE (Cycle 21 Model A fails R26; ICT closed)

**Date:** 2026-11-19. **Code:** `f60ec5c` + `scripts/c23_real_run.py`. **Config:** `a25af5711afb32d4` (c21 21.2.0).
**Data:** Dukascopy M1 bid/ask, dev 2018-01-01..2024-12-31 (1,761 XNYS dates per instrument). Holdout 2012-2014 never
loaded.

## Result

| Step | Result |
|---|---|
| Synthetic gates 1-6 | PASS (6,014 synthetic days, 0 event mismatches) |
| Real-data event parity (engine vs independent reference) | MATCH — 5,283 dates, 0 mismatches |
| Trades produced, 7 years | **NAS100 0, SPX 0, US30 0** |
| R26 gate `>= 100 trades` | **FAIL x3** → all instruments FAIL |
| Doubled-cost run, luck test | Not run (cannot rescue a failed trade-count gate) |

## Where setups die (engine day results, identical in the reference)

| result | NAS100 | SPX | US30 |
|---|---|---|---|
| no_sweep (bias set, no first-breach sweep closing back inside 10:00-11:00) | 1120 | 1061 | 1024 |
| bias_mixed_or_equal | 584 | 646 | 680 |
| no_mss after a sweep | 41 | 38 | 24 |
| early_close_day | 15 | 15 | 15 |
| bad-quote sessions excluded | 0 | 0 | 16 |
| premium_discount_fail / no_target_min_rr / contaminated | 1 | 1 | 2 |

106 sweep days were charted (212 PNGs, decision + outcome, 0 render failures) in `out/c23/real/charts/` (local, not
committed). Spot check NAS100 2021-08-26: Asia-high sweep, MSS, bearish FVG, but price already below PDL, so no
liquidity target at >= 2R → `no_target_min_rr`, correct per the rules.

## Interpretation (brutal)

The rules as written (first-breach sweep of PDH/PDL/Asia inside one hour, then a confirmed 15 m MSS before 11:00, then
a 5 m FVG, PD-array alignment and a >= 2R liquidity target) are jointly so restrictive that real index data almost never
satisfies them. Two independent implementations agree day by day, so this is not a coding bug. It is the rule set.

## Decisions honoured

- Pre-registered fail rule (spec D1/D11): no instrument passes → SHELVE, ICT closed permanently. No rule loosening,
  no visual-metric filters, no cycle 24 ICT variant.
- Known defect recorded, not fixed (irrelevant to the verdict): c21 `widen_costs` widens each OHLC field's spread
  independently, which can make bid high < bid open and trips `validate_m1` (`DataIntegrityError: inconsistent bid
  OHLC`). Any future doubled-cost run with that helper must fix it first.
