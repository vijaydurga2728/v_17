# Cycle 23 real-data event parity + metrics (dev 2018-01-01..2024-12-31, Model A, SMT off)

Metrics version `23.m1` — descriptive only, never a filter.

## Event parity (engine vs independent reference)

| instrument | variant | days | event-level mismatches | parity |
|---|---|---|---|---|
| NAS100 | A | 1761 | 0 | PASS |
| SPX | A | 1761 | 0 | PASS |
| US30 | A | 1761 | 0 | PASS |

## Coverage by category

| category | days |
|---|---|
| excluded | 61 |
| rejected_after_sweep | 106 |
| rejected_pre_sweep | 5116 |

## Near-miss / rejection reasons after a sweep

| reason | days |
|---|---|
| no_mss | 103 |
| premium_discount_fail | 2 |
| no_target_min_rr | 1 |

## Metric medians: winners vs losers (filled trades)

| metric | winners | losers |
|---|---|---|
| sweep_depth | - | - |
| disp_body_ratio | - | - |
| disp_range_atr | - | - |
| fvg_size_atr | - | - |


## Disagreements (first 20)

None.
