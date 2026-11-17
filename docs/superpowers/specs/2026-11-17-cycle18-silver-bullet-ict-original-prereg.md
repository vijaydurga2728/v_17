# Cycle 18 — Silver Bullet v3 "ICT's own rules" (pre-registration)

**Status:** FROZEN 2026-11-17 on user request "fix those differences and rerun silver bullet". Committed before any
v3 code or result.
**Source of rules:** ICT, "2023 ICT Mentorship – ICT Silver Bullet Time Based Trading Model" (YouTube tRq1hyGGtl4), via
the transcript summary at glasp.co (YouTube transcript download was rate-limited):
windows 03-04 / 10-11 / 14-15 NY; minimum trade framework **10 points (index futures) / 15 pips (FX)**; setups aim
for the **draw on liquidity** (previous day high/low, previous week high/low, FVGs, opening gaps); FVG forms in the window;
trades may run past the window.

## Differences fixed vs v2 (cycle 17)
1. No "sweep inside the window" requirement (not in ICT's description).
2. No displacement size thresholds (not in ICT's description).
3. Direction and target = draw on liquidity (PDH/PDL, PWH/PWL), not sweep reversal / session pools.
4. ICT minimum trade framework applied: target distance ≥ 10 pts (NAS100, SPX) / 15 pips (EURUSD, GBPUSD).
5. Rulebook-only filters dropped: R:R ≥ 1.5, SL max distance, FVG ≥ 2× spread.

## Mechanical translation (per slot, per NY date; mid prices for patterns, bid/ask for fills)
- **Levels:** PDH/PDL = high/low of the previous NY weekday (00:00-24:00 NY); PWH/PWL = high/low of the previous
  Monday-Friday NY week.
- **Draw on liquidity:** among the four levels, drop any already traded through between 00:00 NY and window start;
  the draw is the remaining level nearest to the price at window start (mid open of the first window bar).
  Level above → **LONG**, below → **SHORT**. No level left → no trade.
- **Entry:** the first 3-candle FVG in the draw direction with all three candles inside the window
  (bullish: low[c3] > high[c1]; bearish: high[c3] < low[c1]). Limit order at CE after c3 closes, valid until
  window end + 5 min. Long fills when ask low ≤ CE, short when bid high ≥ CE.
- **Stop:** beyond FVG candle 1: long SL = low[c1] − buffer_min, short SL = high[c1] + buffer_min
  (buffer_min as v2: NAS 2 pts, SPX 0.6 pt, FX 2 pips). Distance below buffer_min → set to buffer_min.
- **Target:** the draw level. Must be ≥ 10 pts (indices) / 15 pips (FX) from CE in the trade direction; else no trade.
- **Exit, costs, R, one trade per slot per day:** identical to v2 (cycle 17 pre-reg §2 points 6-7).

## Slots, data, exam — identical to cycle 17
12 slots (3 windows × NAS100, SPX, EURUSD, GBPUSD). Dev NY dates 2018-2024: pass = PF ≥ 1.3 and luck p ≤ 0.05/12
(random-entry null as cycle 17, 5,000 permutations, seed `20261117*1000 + 1100 + slot_index`). Holdout 2025 → end of
data for dev passers, PF ≥ 1.2, run once.

## Outcome
No slot passes → Silver Bullet (all three versions: cycle 1 rulebook, v2, ICT-own v3) is closed. No further variants.
