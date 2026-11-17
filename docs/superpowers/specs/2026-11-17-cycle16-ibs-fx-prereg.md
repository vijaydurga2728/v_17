# Cycle 16 — IBS mean reversion, long + short, 7 FX majors (pre-registration)

**Status:** FROZEN 2026-11-17 on user request "test IBS on fx majors". Committed before any IBS FX result.
**Branch:** `cycle16-ibs-fx` (from `458e6e1`).

## Rule
Identical to cycle 15 (`src/v17/setups/c15_ibs.py`, pre-reg a1588e1 §1): mid-bar IBS signal on the daily close, long
when IBS < lo, short when IBS > hi, entry at the next bar's open (bid/ask), exit per setting, one position at a time,
R unit 1% of signal close.

## Data
`data/bars_d1_fxny/<PAIR>/d1.parquet` (NY 17:00 rollover, built in cycle 12 from the cycle 4B M1 source, real
bid/ask). Pairs: EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD. No fresh pre-2015 data for most pairs, so
there is one exam (recent).

## Step 1 — tuning, signal bars 2015-06-01 → 2021-12-31
Same 4-setting menu as cycle 15. Score per pair = mean R − median random-null mean R (same long/short mix, 2,000
permutations, seed `20261117*1000 + 900 + setting_index`); setting score = average over the 7 pairs; one shared
winner (ties → lowest index).

## Step 2 — one exam, signal bars 2022-01-01 → end of data
Per pair: PF ≥ 1.3 and luck test p ≤ **0.05/7 = 0.007143** (10,000 permutations, same-mix random null,
seed `20261117*1000 + 950 + pair_index`). Long and short sides reported separately.
FTMO simulation (cycle 15 §6 method, 0.5% per R) for passing pairs, and for all passing pairs combined.

## Limits
- Overnight swap/financing is not modelled (holds of 1-5 days).
- 2018-2024 FX data was used in cycle 12 for a different strategy (RSI2).
- If no pair passes, IBS on FX is dropped; no re-tuning.
