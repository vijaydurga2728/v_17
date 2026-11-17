# Cycle 15 — IBS mean reversion, long + short, NAS100 and SPX (pre-registration)

**Status:** FROZEN 2026-11-17. User "yes to all" on revised Q1-Q7. Committed before any IBS code or result.
**Branch:** `cycle15-ibs-long-short` (from `803850e`).
**Source idea:** Pagonidis (2013), "The IBS Effect: Mean Reversion in Equity ETFs" (NAAIM): close near the day's
low → next day up; close near the high → next day down.

## 1. Rule (one combined long + short system per market, one position at a time)

- `IBS = (C − L) / (H − L)` on the daily **mid** bar; bars with H = L have no signal.
- Signal on bar D's close: IBS < `lo` → **long**; IBS > `hi` → **short**.
- **Entry at the open of bar D+1** (broker session reopens 18:00 ET right after D's 17:00 ET close; no look-ahead).
  Long fills `ask_o`, short fills `bid_o`.
- Exit (tuned, see §3):
  - `next_close`: close of the entry bar D+1.
  - `ibs_cross`: first close (from the entry bar on) where IBS > `hi` for a long / IBS < `lo` for a short, else the
    close of the 5th bar after entry starts (entry bar + 4).
  Long exits `bid_c`, short exits `ask_c`.
- After an exit at bar X's close, a new signal on bar X itself is allowed (its entry is X+1's open).
- R unit = 1% of the signal bar's mid close; R = pnl / R unit.

## 2. Markets and data

- NAS100 (`USATECHIDXUSD`) and SPX (`USA500IDXUSD`).
- **Broker bars:** `data/bars_d1_ny17/<SYM>/d1.parquet` (NY 17:00 rollover; matches IC Markets MT5 D1), real bid/ask.
- **Fresh bars:** user's Dukascopy daily CSVs (cycle 14 loader: flats dropped, cut at 2011-08-31), bid = ask, fixed
  cost **0.03R per trade** subtracted.

## 3. Step 1 — tuning, 2016-01-01 → 2021-12-31 (broker bars)

Menu (4 settings, nothing else): levels {(0.1, 0.9), (0.2, 0.8)} × exit {next_close, ibs_cross}.
Score per market = mean R − median mean R of the random null (§4, 2,000 permutations,
seed `20261117*1000 + 700 + setting_index`); setting score = average over the 2 markets; winner = highest
(ties → lowest setting_index). One shared setting.

## 4. Luck test (all exams)

Random null keeps the strategy's exact numbers of longs and shorts: each permutation draws that many random signal
bars (without replacement) from all eligible bars in the window, assigns the long/short mix, applies the same exit rule
and fills, and takes the mean R. **10,000 permutations**, p = (count ≥ observed + 1)/(10,001).

## 5. Step 2 — two exams with the tuned winner only

| Exam | Window (signal bars) | Data |
|---|---|---|
| Fresh | 1991-09-01 → 2011-08-31 | Dukascopy daily, 0.03R cost |
| Recent | 2022-01-01 → end of data | broker bars, real bid/ask |

Seeds: `20261117*1000 + 800 + 2*market_index + exam_index` (fresh = 0, recent = 1).
**Pass for a market:** on **both** exams, PF ≥ 1.3 **and** luck p ≤ **0.05/4 = 0.0125**.
Long and short sides are also reported separately (not gating).

## 6. FTMO simulation (Q6, reporting, only for passing markets)

On recent-exam trades, risk 0.5% of equity per 1R. Daily P&L = sum of R of trades exiting that day × 0.5%.
For every possible start day: walk forward until equity reaches +10% (pass), falls to −10% overall or loses ≥ 5% in
a single day (fail), or data ends (unfinished). Report pass / fail / unfinished shares and median trading days to pass.
If both markets pass, also simulate them combined.

## 7. Outcome rule (Q7)

If no market passes the recent (2022 → today) exam, IBS is dropped. No extra tuning, no re-runs.

## 8. Code

`src/v17/setups/c15_ibs.py`, `tests/unit/c15/`, `scripts/run_c15_ibs.py`; outputs `out/c15/`.
