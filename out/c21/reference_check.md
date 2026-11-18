# Cycle 21 independent re-implementation check (synthetic markets only)

Main engine `src/v17/smc_sb` vs `scripts/c21_reference_impl.py` (no shared strategy code).
Each row compares every weekday after a 1-month warm-up: day outcome (trade or exact rejection reason)
and, for trades, all fields below plus R (tolerance 1e-9).

| seed | span | variant | days | outcome mismatches | trades main | trades ref | field mismatches | max abs dR | result |
|---|---|---|---|---|---|---|---|---|---|
| 7 | 2019-2020 | A | 500 | 0 | 4 | 4 | 0 | 0.0e+00 | MATCH |
| 7 | 2019-2020 | B | 500 | 0 | 0 | 0 | 0 | 0.0e+00 | MATCH |
| 7 | 2019-2020 | SMT | 500 | 0 | 3 | 3 | 0 | 0.0e+00 | MATCH |
| 11 | 2021-2022 | A | 500 | 0 | 10 | 10 | 0 | 0.0e+00 | MATCH |
| 11 | 2021-2022 | B | 500 | 0 | 0 | 0 | 0 | 0.0e+00 | MATCH |
| 11 | 2021-2022 | SMT | 500 | 0 | 4 | 4 | 0 | 0.0e+00 | MATCH |
| 23 | 2023-2024 | A | 500 | 0 | 9 | 9 | 0 | 0.0e+00 | MATCH |
| 23 | 2023-2024 | B | 500 | 0 | 1 | 1 | 0 | 0.0e+00 | MATCH |
| 23 | 2023-2024 | SMT | 500 | 0 | 5 | 5 | 0 | 0.0e+00 | MATCH |
| 42 | 2019-2020 | A | 500 | 0 | 1 | 1 | 0 | 0.0e+00 | MATCH |
| 42 | 2019-2020 | B | 500 | 0 | 0 | 0 | 0 | 0.0e+00 | MATCH |
| 42 | 2019-2020 | SMT | 500 | 0 | 0 | 0 | 0 | 0.0e+00 | MATCH |
| 101 | 2021-2022 | A | 500 | 0 | 3 | 3 | 0 | 0.0e+00 | MATCH |
| 101 | 2021-2022 | B | 500 | 0 | 0 | 0 | 0 | 0.0e+00 | MATCH |
| 101 | 2021-2022 | SMT | 500 | 0 | 3 | 3 | 0 | 0.0e+00 | MATCH |
| 202 | 2023-2024 | A | 500 | 0 | 3 | 3 | 0 | 0.0e+00 | MATCH |
| 202 | 2023-2024 | B | 500 | 0 | 0 | 0 | 0 | 0.0e+00 | MATCH |
| 202 | 2023-2024 | SMT | 500 | 0 | 2 | 2 | 0 | 0.0e+00 | MATCH |

## Outcome coverage (main engine, all seeds)

| variant | outcome | days |
|---|---|---|
| A | bias_insufficient_structure | 20 |
| A | bias_mixed_or_equal | 1098 |
| A | early_close_day | 24 |
| A | excluded_session_bad_quotes | 12 |
| A | missing_m1 | 63 |
| A | no_fvg_after_mss | 79 |
| A | no_mss | 308 |
| A | no_sweep | 1164 |
| A | no_target_min_rr | 9 |
| A | not_xnys_session | 100 |
| A | premium_discount_fail | 68 |
| A | reference_window_contaminated | 9 |
| A | trade | 30 |
| A | unfilled_expired | 16 |
| B | bias_insufficient_structure | 20 |
| B | bias_mixed_or_equal | 1098 |
| B | early_close_day | 24 |
| B | excluded_session_bad_quotes | 12 |
| B | missing_m1 | 63 |
| B | no_fvg_after_mss | 79 |
| B | no_mss | 308 |
| B | no_sweep | 1164 |
| B | not_xnys_session | 100 |
| B | ote_proximal_outside_zone | 120 |
| B | premium_discount_fail | 1 |
| B | reference_window_contaminated | 9 |
| B | trade | 1 |
| B | unfilled_expired | 1 |
| SMT | bias_insufficient_structure | 20 |
| SMT | bias_mixed_or_equal | 1098 |
| SMT | early_close_day | 24 |
| SMT | excluded_session_bad_quotes | 12 |
| SMT | missing_m1 | 63 |
| SMT | no_fvg_after_mss | 32 |
| SMT | no_mss | 142 |
| SMT | no_sweep | 1164 |
| SMT | no_target_min_rr | 5 |
| SMT | not_xnys_session | 100 |
| SMT | premium_discount_fail | 27 |
| SMT | reference_window_contaminated | 9 |
| SMT | smt_no_divergence | 282 |
| SMT | trade | 17 |
| SMT | unfilled_expired | 5 |

## Exit coverage (trades)

| variant | exit | gap-through | trades |
|---|---|---|---|
| A | force_close_16 | False | 2 |
| A | stop | False | 27 |
| A | target | False | 1 |
| B | stop | False | 1 |
| SMT | stop | False | 16 |
| SMT | target | False | 1 |

**Overall: MATCH**
