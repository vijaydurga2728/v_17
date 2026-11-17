# Cycle 14 — RSI(2): legal tuning on 2016-2024, one exam on untouched 1991-2011 data (pre-registration)

**Status:** FROZEN 2026-11-17. User "yes to all" on Q1-Q11. Committed before any tuning result or any strategy run
on the 1990-2011 data (only a data-quality audit of that data was done).
**Branch:** `cycle14-rsi2-fresh-data` (from `ba74bc2`).

## 1. Markets

NAS100 (`USATECHIDXUSD`) and SPX (`USA500IDXUSD`). US30 excluded (Dukascopy daily data starts 2013-09).

## 2. Step 1 — tuning (2016-2024, broker-matched bars)

- Data: NY-17:00 D1 bars `data/bars_d1_ny17/<SYM>/d1.parquet` (cycle 13), real bid/ask fills.
- Window: signal bars 2016-01-01 → 2024-12-31.
- **Menu (8 settings, nothing else):** RSI(2) buy level {< 5, < 10} × 200-day filter {off, on (close > SMA200)}
  × exit {close > SMA(5), close > SMA(10)}. Time cap 10 bars, long only, R unit 1% of signal close — unchanged.
- **Score:** for each market, `edge = mean R − median mean R of the random-entry null` (null = random long entries
  from all eligible window bars, same exit rule; 2,000 permutations, seed `20261117*1000 + 400 + setting_index`).
  Setting score = average edge over NAS100 and SPX. **Winner = highest score; one shared setting.**
  Ties broken by setting_index order (buy level, filter, exit as listed).

## 3. Step 2 — the one fresh exam (1991-2011)

- Data: Dukascopy daily bid/ask CSVs supplied by the user 2026-11-17
  (`USATECHIDXUSD_Daily_{Bid,Ask}_1990.11.06_2014.12.30.csv`, `USA500IDXUSD_Daily_{Bid,Ask}_1989.12.31_2014.12.30.csv`).
  Bars are labelled 01:00 EET = 18:00 ET session open (matches the broker's daily bars).
- Cleaning: drop flat bars (open = high = low = close); keep data up to **2011-08-31** only (Sep 2011 – Jan 2012 has
  a ~4-month hole and a fake +14% SPX jump; 2012-2014 is dropped).
- Window: signal bars **1991-09-01 → 2011-08-31** (earlier bars warm up the indicators, incl. SMA200).
- **Candidates (3):** (a) tuned winner from step 1; (b) original RSI2 (buy < 10, no filter, SMA(5) exit);
  (c) RSI2 + 200-day filter (buy < 10, filter on, SMA(5) exit). If the winner equals (b) or (c), only 2 distinct
  candidates are run, but α stays 0.05/6.
- Costs: bid = ask before 2012, so a fixed **0.03% round-trip cost** per trade is subtracted
  (= 0.03R with R unit 1% of price).
- **Pass (per candidate, per market):** PF ≥ 1.3 **and** luck-test p ≤ **0.05/6 = 0.008333**.
  Luck test: random long entries from all eligible window bars, same exit rule, mean R statistic,
  **10,000 permutations**, p = (count ≥ observed + 1)/(10,001), seed `20261117*1000 + 600 + 3*market_index +
  candidate_index`. R², per-year results and max drawdown are reported, not gating.
- **Outcome rule (Q11):** if no candidate passes on either market, RSI2 is closed for good.
- No re-run, no change of candidates, windows or thresholds after the fresh results are seen.

## 4. Code

`v17.setups.c12_rsi2_fx` gains `rsi_buy` and `exit_sma` options (defaults 10 and 5, so cycles 12/13 are unchanged;
existing parity test still applies). Runner: `scripts/run_c14_rsi2_fresh.py`; outputs `out/c14/`.
