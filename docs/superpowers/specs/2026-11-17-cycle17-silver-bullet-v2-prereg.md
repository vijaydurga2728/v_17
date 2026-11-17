# Cycle 17 — ICT Silver Bullet v2 (bug-fixed, sweep-driven, long + short) — pre-registration

**Status:** FROZEN 2026-11-17. User "yes to all" on Q1-Q5. Committed before any v2 code or result.
**Branch:** `cycle17-silver-bullet-v2` (from `7db390d`).

## 0. Why a v2

Audit of cycle 1 (`.worktrees/sb-6-engine-gate`) found:
1. **Bug:** displacement tested on FVG candle 3 instead of candle 2 (`fvg_sb.py` stamps the FVG with candle 3's time;
   `engine_runner.py` tests that bar).
2. **Bug:** short-side SL/TP checked on bid instead of ask (`_simulate_fill`).
3. **Bug:** pending-order expiry (window end + 5 min) not applied.
4. **Gap:** only 1 of 6 engines (London CE, FX) was ever run.
5. **Our deviation, removed (Q2):** D1 EMA20/structure bias filter and fixed daily direction. v2 lets the sweep decide.

v2 is a clean re-implementation with the frozen rulebook values (`sb_constants.py`) and the fixes above.

## 1. Slots (12)

Windows (NY time): LDN 03:00-04:00, AM 10:00-11:00, PM 14:00-15:00 × symbols NAS100 (`USATECHIDXUSD`), SPX
(`USA500IDXUSD`), EURUSD, GBPUSD. `slot_index` = window order (LDN, AM, PM) × 4 + symbol order (NAS, SPX, EURUSD, GBPUSD).
Entry model: CE (FVG midpoint). One trade per slot per NY date.

## 2. Rules per slot and NY date (mid prices for pattern logic, bid/ask for fills)

1. **Pools at window start:** session high/low from 00:00 NY to window start; previous-hour high/low (window start −60
   min to window start).
2. **Sweep (inside the window):** the first bar whose mid low is below either low pool → **LONG** day; whose mid high
   is above either high pool → **SHORT** day. If the first such bar sweeps both sides, the slot skips that day.
   Sweep extreme = that bar's extreme, extended by later bars while the setup is pending.
3. **Displacement + FVG (after the sweep, inside the window):** first 3-candle FVG in the trade direction
   (bullish: low[c3] > high[c1]; bearish: high[c3] < low[c1]) whose **candle 2** has body/range ≥ 0.65 and
   range ≥ 1.5 × ATR14 (M1, mean true range of the 14 bars ending at candle 1), with candle 2 at or after the sweep bar
   and candle 3 before window end. FVG height must be ≥ 2 × spread at candle 3.
4. **Order:** limit at CE, placed after candle 3 closes, valid until window end + 5 min.
   - SL: sweep extreme ∓ buffer_min; if distance > buffer_max → no trade; if distance < buffer_min → distance = buffer_min.
   - TP: nearest opposing pool beyond CE (session/previous-hour high for longs, low for shorts), else CE ± fallback.
   - R:R = TP distance / SL distance; < 1.5 → no trade.
   - Constants (rulebook): FX buffer min 2 pips, max 15 pips, fallback 20 pips. NAS100 buffer min 2 pts, max 20 pts,
     fallback 15 pts. **SPX** (rulebook silent): NAS100 values × 0.3 (price ratio): min 0.6, max 6, fallback 4.5 pts.
5. **Fill:** long when ask low ≤ CE, short when bid high ≥ CE; entry price = CE.
6. **Exit (from the fill bar on):** long SL if bid low ≤ SL, TP if bid high ≥ TP; short SL if ask high ≥ SL, TP if
   ask low ≤ TP; both in one bar → SL. On the fill bar only SL is checked. Else exit at the close of the bar at
   window end + 60 min (bid close long / ask close short).
7. **Costs:** 0.5 pip (FX) / 0.5 pt (indices) adverse slippage on SL and time exits; none on limit entry/TP.
   FX commission $3/lot/side = 0.6 pip round trip. R = net pnl / SL distance.
8. Not applied (stated deviation): news blackout and spread guard (calendar dependency).

## 3. Data and windows

Paired M1: NAS100, EURUSD, GBPUSD from `.worktrees/sb-6-engine-gate/data`; SPX from `data/bars_m1_paired/`.
**Dev:** NY dates 2018-01-01 → 2024-12-31. **Holdout:** 2025-01-01 → end of data, only for dev passers, run once.

## 4. Gates

- **Dev:** PF ≥ 1.3 and luck test p ≤ **0.05/12 = 0.004167**.
- **Luck test:** each permutation re-enters every real trade at a random minute inside the same window on a random dev
  date for that slot, with the real long/short mix shuffled, each trade's own SL and TP distances, market entry at the
  bar open (ask long / bid open short) + 0.5 slippage, same exit rules and costs. Statistic mean R; **5,000
  permutations**; p = (count ≥ observed + 1)/(5,001); seed `20261117*1000 + 1000 + slot_index`.
- **Holdout:** PF ≥ 1.2.
- **Outcome rule (Q5):** no slot passes → Silver Bullet closed, no further tuning.
