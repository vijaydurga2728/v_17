# Cycle 20 — Silver Bullet v5: v4 + SMT + OTE + IPDA, fresh markets (pre-registration)

**Status:** FROZEN 2026-11-18. User "yes to all" on Q1-Q6 and Q7 = B (gold dropped). Committed before any v5 code or
result.
**Sources:** ICT SMT lesson (pair vs DXY; NQ vs ES; SMT confirms the stop hunt, not an entry), 2022 ICT Mentorship ep. 35
(SMT around 09:30, dealing range, OTE), OTE 62-79% with 70.5% key level; cycle 19 v4 rules (`2026-11-17-cycle19-...`).

## Markets (never used for Silver Bullet) and SMT partners
| Market | SMT partner | Relation |
|---|---|---|
| US30 `USA30IDXUSD` | SPX `USA500IDXUSD` | moves with |
| USDJPY, USDCAD, USDCHF | DXY `DOLLARIDXUSD` | moves with |
| AUDUSD, NZDUSD | DXY `DOLLARIDXUSD` | moves against |

18 slots = 6 markets × windows 03-04 / 10-11 / 14-15 NY. `slot_index` = window order × 6 + market order as listed
(US30, USDJPY, USDCAD, USDCHF, AUDUSD, NZDUSD).

## Rules (mid prices for patterns, bid/ask for fills) — order matters
1. **IPDA draw:** candidates = PDH/PDL, PWH/PWL and the 20-, 40-, 60-trading-day high/low (days before today). Drop any
   traded through between 00:00 NY and window start. Nearest remaining level to the window-start mid open sets direction
   (above → LONG) and is the target.
2. **Sweep (in window):** as v4 (nearer of session-since-00:00 / previous-hour pool on the opposite side).
3. **SMT (new):** over the partner's bars from window start to the sweep bar's timestamp, using the partner's own pools
   (nearer of its session/previous-hour level): positive partner must **not** break its matching pool (LONG: no new low;
   SHORT: no new high); inverse partner must **not** break the opposite pool (LONG: DXY no new high; SHORT: no new low).
   Missing partner data → no trade.
4. **MSS (close-confirmed)** and **displacement FVG with candle 2 in [sweep, MSS]**: as v4.
5. **Location (changed):** entry must be below (LONG) / above (SHORT) the midpoint of the previous 20 trading days'
   high-low range.
6. **OTE entry (changed):** leg low = lowest mid low from the sweep bar to max(FVG candle 3, MSS bar); leg high = highest
   mid high over the same bars (mirror for SHORT). Limit at leg_high − 0.705 × (leg_high − leg_low) (LONG) /
   leg_low + 0.705 × (leg_high − leg_low) (SHORT), placed after max(c3, MSS), valid to window end + 5 min.
   SL = leg extreme ∓ buffer_min. TP = the draw. Require TP distance ≥ minimum frame and R:R ≥ 2.
7. Fill, exits (window end + 60 min max), costs, one trade per slot per day: as cycles 17-19.

## Per-market constants (existing conventions, not tuned)
| Market | buffer_min | slippage | commission (round trip) | minimum frame |
|---|---|---|---|---|
| US30 | 2 pts | 0.5 pt | 0 | 10 pts |
| USDJPY | 0.02 (2 pips) | 0.005 | 0.006 (0.6 pip) | 0.15 (15 pips) |
| USDCAD, USDCHF, AUDUSD, NZDUSD | 0.0002 | 0.00005 | 0.00006 | 0.0015 |

## Exam
- NY dates **2018-01-01 → end of data** (never used for Silver Bullet on these markets).
- Pass (per slot): PF ≥ 1.3 and luck test p ≤ **0.05/18 = 0.002778** (cycle 17 random-entry null, 5,000 permutations,
  seed `20261118*1000 + 100 + slot_index`).
- Order: code + unit tests → independent re-implementation must match trade by trade (NY AM US30 and AUDUSD) →
  hand-check table → results.
- No slot passes → Silver Bullet closed (user promise Q5).
