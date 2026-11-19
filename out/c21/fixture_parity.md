# Cycle 21 targeted fixture parity (review round 3, section 3)

Main engine vs independent reference on hand-designed synthetic days; each row must match exactly
AND satisfy its required assertion.

| fixture | requirement | model | expiry | result | detail |
|---|---|---|---|---|---|
| gap_long_stop | Gap-through long stop: fill at opening bid minus 0.5 | A | 11:05 | PASS | stop @ 99.4000 (10:35), R -2.4444 |
| gap_short_stop | Gap-through short stop: fill at opening ask plus 0.5 | A | 11:05 | PASS | stop @ 100.6000 (10:35), R -2.4444 |
| force_close_1559 | Force close at the real 15:59 bar (control for case 4) | A | 11:05 | PASS | force_close_16 @ 102.4000 (15:59), R +0.8889 |
| missing_1559 | Missing 15:59 bar: no invented 16:00 price; flagged data_gap | A | 11:05 | PASS | force_close_16 @ 102.4000 (15:58), R +0.8889 |
| early_close_no_entry | XNYS early-close date: no new entries | A | 11:05 | PASS | early_close_day |
| ote_valid | Model B: proximal edge inside the 62-79% zone -> order | B | 11:05 | PASS | target @ 109.0000 (10:47), R +8.2222 |
| ote_invalid | Model B: proximal edge outside the zone -> rejected | B | 11:05 | PASS | ote_proximal_outside_zone |
| ote_overlap_not_proximal | OTE + FVG: FVG overlaps the zone but proximal edge outside | B | 11:05 | PASS | ote_proximal_outside_zone |
| ote_upper_boundary_inclusive | OTE zone boundary is inclusive | B | 11:05 | PASS | target @ 109.0000 (10:47), R +8.2222 |
| ote_upper_boundary_outside | Just outside boundary | B | 11:05 | PASS | ote_proximal_outside_zone |
| one_pending_then_rescan | One pending order; cancellation permits a later distinct setup | A | 10:40 | PASS | unfilled_expired |
| fill_bar_target_ignored | Target evaluation begins on the bar after the fill | A | 11:05 | PASS | target @ 109.0000 (10:47), R +8.2222 |
| fill_bar_stop | Stop can trigger on the fill bar | A | 11:05 | PASS | stop @ 100.7000 (10:32), R -1.0000 |

**Overall: PASS**
