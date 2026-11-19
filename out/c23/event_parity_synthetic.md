# Cycle 23 gate 6 — event parity + metrics (SYNTHETIC ONLY)

Metrics version `23.m1` — descriptive only, never a filter.

## Event parity (engine vs independent reference)

| instrument | variant | days | event-level mismatches | parity |
|---|---|---|---|---|
| FIX_base | A | 1 | 0 | PASS |
| FIX_early_close_no_entry | A | 1 | 0 | PASS |
| FIX_fill_bar_stop | A | 1 | 0 | PASS |
| FIX_fill_bar_target_ignored | A | 1 | 0 | PASS |
| FIX_force_close_1559 | A | 1 | 0 | PASS |
| FIX_gap_long_stop | A | 1 | 0 | PASS |
| FIX_gap_short_stop | A | 1 | 0 | PASS |
| FIX_missing_1559 | A | 1 | 0 | PASS |
| FIX_one_pending_then_rescan | A | 1 | 0 | PASS |
| FIX_ote_invalid | B | 1 | 0 | PASS |
| FIX_ote_overlap_not_proximal | B | 1 | 0 | PASS |
| FIX_ote_upper_boundary_inclusive | B | 1 | 0 | PASS |
| FIX_ote_upper_boundary_outside | B | 1 | 0 | PASS |
| FIX_ote_valid | B | 1 | 0 | PASS |
| SEED101 | A | 500 | 0 | PASS |
| SEED101 | B | 500 | 0 | PASS |
| SEED11 | A | 500 | 0 | PASS |
| SEED11 | B | 500 | 0 | PASS |
| SEED202 | A | 500 | 0 | PASS |
| SEED202 | B | 500 | 0 | PASS |
| SEED23 | A | 500 | 0 | PASS |
| SEED23 | B | 500 | 0 | PASS |
| SEED42 | A | 500 | 0 | PASS |
| SEED42 | B | 500 | 0 | PASS |
| SEED7 | A | 500 | 0 | PASS |
| SEED7 | B | 500 | 0 | PASS |

## Coverage by category

| category | days |
|---|---|
| excluded | 399 |
| filled | 40 |
| rejected_after_sweep | 975 |
| rejected_pre_sweep | 4582 |
| unfilled_expired | 18 |

## Near-miss / rejection reasons after a sweep

| reason | days |
|---|---|
| no_mss | 616 |
| no_fvg_after_mss | 158 |
| ote_proximal_outside_zone | 123 |
| premium_discount_fail | 69 |
| trade | 40 |
| unfilled_expired | 18 |
| no_target_min_rr | 9 |

## Metric medians: winners vs losers (filled trades)

| metric | winners | losers |
|---|---|---|
| sweep_depth | 0.500 (n=9) | 2.805 (n=31) |
| disp_body_ratio | 0.857 (n=9) | 0.741 (n=31) |
| disp_range_atr | 2.227 (n=9) | 3.572 (n=31) |
| fvg_size_atr | 0.636 (n=9) | 0.755 (n=31) |
| sweep_close_inside (share true) | 1.000 (n=40) | |

## Disagreements (first 20)

None.
