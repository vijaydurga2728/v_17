# Cycle 19 — Silver Bullet v4: full ICT sequence (pre-registration)

**Status:** FROZEN 2026-11-17. User "yes to all" on Q1-Q5. Committed before any v4 code or result.
**Sources:** ICT 2023 Silver Bullet lesson (windows, 10 pt / 15 pip minimum frame, draw on liquidity);
`carreypro/ict-trading-model` skill sequence (bias → liquidity objective → premium/discount → sweep → displacement +
FVG → close-confirmed MSS → retracement → invalidation/target → R:R), read only, not installed; ICT short-term
high/low definition (a candle whose high is above both neighbours' highs; mirror for lows).

## Rules (per slot, per NY date; mid prices for patterns, bid/ask for fills)
Window [ws, we) = 03-04 / 10-11 / 14-15 NY. Steps must occur in this order:
1. **Draw on liquidity → direction & target** (as cycle 18): nearest of PDH/PDL/PWH/PWL not traded through between 00:00
   NY and ws, relative to the mid open at ws. Above → LONG, below → SHORT. None → no trade.
2. **Sweep (in window):** LONG: first bar with mid low below the nearer of {session low since 00:00 NY, previous-hour low};
   SHORT: mirror with highs. Opposite-side sweeps are ignored.
3. **MSS (close-confirmed):** reference = the most recent ICT short-term high (LONG) / low (SHORT) at bar j with
   00:00 NY ≤ j−1 and j+1 < sweep bar. MSS bar = first bar after the sweep, inside the window, whose mid close is above
   (below) that reference. No reference or no MSS → no trade.
4. **Displacement + FVG:** the first FVG in the trade direction whose candle 2 lies between the sweep bar and the MSS bar
   (inclusive) and is a displacement candle (body/range ≥ 0.65, range ≥ 1.5 × ATR14 M1 ending at candle 1); candle 3
   inside the window; FVG height ≥ 2 × spread at candle 3.
5. **Premium/discount:** CE must be below (LONG) / above (SHORT) the midpoint of the previous weekday's range
   ((PDH + PDL) / 2).
6. **Order:** limit at CE, placed after max(candle 3, MSS bar) closes, valid until we + 5 min.
   SL = sweep extreme (extended until placement) ∓ buffer_min (NAS 2 pts, SPX 0.6, FX 2 pips); distance below
   buffer_min → buffer_min. TP = the draw. Require TP distance ≥ 10 pts (indices) / 15 pips (FX) and R:R ≥ 2.
7. **Fill, exits, costs, R, one trade per slot per day:** identical to cycle 17 §2 points 5-7
   (exit at we + 60 min at the latest).

## Exam
- **Decision (one shot): NY dates 2015-01-01 → 2017-12-31**, all 12 slots (3 windows × NAS100, SPX, EURUSD, GBPUSD).
  Pass for a slot: PF ≥ 1.3 and luck test p ≤ 0.05/12 (cycle 17 random-entry null, 5,000 permutations,
  seed `20261117*1000 + 1300 + slot_index`).
- **Extra check (report):** EURUSD 2010-2014. **Information only:** 2018 → end of data (already-seen years).
- **Order of work:** code + unit tests → independent re-implementation must match trade by trade (NY AM NAS100 and
  EURUSD, exam period) → hand-check table → results.
- **Outcome:** no slot passes → Silver Bullet and all ICT variants closed for good.
