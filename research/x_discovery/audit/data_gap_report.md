# Data Gap Report

**Date:** 2026-11-14

## Gaps that block a candidate outright

| Missing data | Blocks | Typical source | Cost / effort | Comment |
|---|---|---|---|---|
| US single-stock 1–5 min bars + exchange volume, survivorship-free, ≥1,000 names, 2016+ | #1 ORB stocks-in-play | Polygon.io, Databento, QuantConnect (in-platform), Norgate (daily only) | Paid; tens to hundreds of GB | Even with data, FTMO offers only a limited set of stock CFDs. The tradeable universe would not match the tested universe. **Not worth acquiring for an FTMO goal.** |
| Bond and ex-US equity total-return series | #4 GEM | Yahoo/Stooq ETF closes (AGG, EFA, SPY, BIL) | Free, monthly | Blocked by user's universe directive (no bonds), not by data. |
| Exchange futures volume / footprint / order flow | #10 80% rule (final step), any microstructure idea | CME DataMine, Databento MBO | Paid, large | Not needed for any shortlisted candidate. |
| Proprietary "Intelligent Balance" indicator | #11 | Vendor | — | Closed. Untestable. |

## Gaps that need engineering only (data already on disk)

| Gap | Needed by | Work |
|---|---|---|
| US30 not ingested | #2, #3, #7 | Run the existing M1 ingest on `USA30IDXUSD_1 Min_{Bid,Ask}_2015.01.01_2026.10.14.csv` |
| US500 D1 cache missing | #3, #5, #6 | Resample from `data/bars_m1_paired/USA500IDXUSD` |
| USDCHF / USDCAD / GBPUSD / EURUSD M1 paired (only D1 for some) | none shortlisted at M1 | Only if an FX intraday idea is chosen later |
| **Cash-session bars** (09:30–16:00 America/New_York, DST-aware) for indices | #2, #5, #6, #7 | New resampler variant; current D1/M5 are full CFD session. Must handle US holidays and half-days. |
| Swap/financing cost model for multi-day holds | #3 EWMAC | Not in current cost model (RSI2 holds ≤10 days and ignores swap). |
| Real SPY/ES reference series to check CFD fidelity | all index candidates | Optional: free SPY daily (Stooq) to confirm USA500IDXUSD tracks cash closes. Worth one sanity check. |

## Proxy risks to state in any spec

1. **CFD ≠ ETF/future.** Spread is wider than SPY's, and there are no dividends. Krueger's result shows that spread alone erased the ORB edge on index CFDs.
2. **Tick volume ≠ exchange volume.** It affects VWAP (Noise Area trailing stop) and any relative-volume rule.
3. **Data vendor single-source.** All prices come from Dukascopy. No cross-vendor check has been done in v17.
4. **US500 end date 2026-10-14.** Cycle 6 holdout already uses 2024-01-01 → 2026-10-14 on US500. A new US500 test should reuse the same split so cycle 6 holdout stays sealed and the new holdout stays unseen.

## Holdout contamination status (do not open)

| Series | Window | Status |
|---|---|---|
| USATECHIDXUSD D1 | 2025-01-01 → 2026-10-18 | **Opened** (RSI2 holdout, TSM/DON eval). Contaminated for any NAS100 daily idea. |
| FX majors D1 | 2025-01-01 → 2026 | **Opened** (RSI2 FX exploration, pooled scheme-1, cycle 5). |
| USATECHIDXUSD M1 intraday | 2025–2026 | Not used by ORB/Gap (shelved at dev). Market regime is still known via the D1 holdout. |
| USA500IDXUSD M1/M5 | 2024-01-01 → 2026-10-14 | **Sealed** (cycle 6 holdout, not yet run). |
| USDJPY / AUDUSD M5 | 2024-01-01 → 2026-10-14 | Sealed (cycle 6). D1 2025+ opened in FX explorations. |
| USA30IDXUSD | all | Never touched. Cleanest confirmation series available. |
