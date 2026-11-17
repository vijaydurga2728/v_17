# Cycle 11 — RSI(2) cross-index replication on SPX and US30 (pre-registration)

**Status:** FROZEN 2026-11-17 on user request "run RSI2 on other indices like SPX and US30". Committed before any
SPX/US30 RSI2 result was computed.
**Branch:** `cycle11-rsi2-cross-index` (from `a73e2b5`).

## 1. Hypothesis

The Connors RSI(2) long-only edge found on NAS100 in cycle 4B also exists on **SPX** (`USA500IDXUSD`) and **US30**
(`USA30IDXUSD`). If it does, running RSI2 on all three raises trade frequency (NAS100 alone: ~15 trades/year).

## 2. Rules — identical to cycle 4B, no changes

- Code: `src/v17/backtest/rsi2_runner.py::run_rsi2_oos_batch` and `src/v17/setups/rsi2_constants.py`, unchanged
  since lock commit `1465ef3` (verified by `git diff` 2026-11-17).
- Entry: D1 close RSI(2) < 10 → long at next D1 open (mid) + 0.5 pt. Exit: close > SMA(5), else TIME_CAP 10 bars.
  R unit = 1% of signal close. No stop.
- New engine configs only: `RSI2EngineConfig("RSI2-USA500IDXUSD", "USA500IDXUSD", 1)` and
  `RSI2EngineConfig("RSI2-USA30IDXUSD", "USA30IDXUSD", 1)`.

## 3. Data

- SPX: `data/bars_m1_paired/USA500IDXUSD/` (existing, cycle 6 ingest).
- US30: ingest `USA30IDXUSD_1 Min_{Bid,Ask}_2015.01.01_2026.10.14.csv` (Dukascopy, user's Documents folder) with
  `v17.data.c6_pipeline.ingest_m1_paired` into `data/bars_m1_paired/USA30IDXUSD/`.
- D1 bars: `v17.data.resample.resample_paired(m1, TF.D1)` on **UTC days**, exactly as cycle 4B built NAS100 D1.
  Written to `data/bars_d1/<SYMBOL>/{dev,holdout}/year=YYYY/` with dev = 2015-2024, holdout = 2025+.

## 4. Windows

- **Dev:** cycle 4B walk-forward, `generate_folds()` — 7 anchored folds, OOS years 2018-2024.
- **Holdout:** 2025-01-01 → 2026-10-14 (data end). Run only for a symbol that passes dev.

## 5. Gates

**Dev (per symbol)** — same standard RSI2-NAS100 was advanced on:
- G1 PF ≥ 1.3, G2 trades ≥ 25 (relaxed floor, as 4B), G4 R² ≥ 0.80, G5 2× slippage PF ≥ 1.1 (`evaluate_secondary`).
- G3 (all folds positive) is **reported, not gating**, because NAS100 itself failed G3 and was advanced.
- **Spread-cost check (new, gating):** PF ≥ 1.3 after subtracting each symbol's median dev M1 spread
  (`ask_c − bid_c`, RTH and non-RTH) once per trade, converted to R by the trade's R unit.
- **Luck test (scheme-1 random-entry MCPT, `run_scheme1_mcpt_rsi2`):** statistic **mean R, registered here in
  advance** (cycle 4B registered PF and swapped later; that swap is not repeated). 10,000 permutations.
  p = (count(null mean R ≥ observed) + 1) / (10,000 + 1), computed from the saved null distribution.
  **α = 0.05 / 2 = 0.025** (two new symbols).

**Holdout (per symbol that passed dev):** PF ≥ 1.3, WR ≥ 50%, max drawdown < 10R (cycle 4B holdout criteria), and
holdout luck test mean-R p ≤ 0.025 (same method).

**Acceptance:** dev pass AND holdout pass. Otherwise that symbol is SHELVED; no threshold or parameter changes.

## 6. Reported, not gating

- Trades per year per symbol, and combined with NAS100.
- Overlap: share of SPX/US30 trades whose entry date also has a NAS100 RSI2 entry.
- Combined 3-symbol R curve and its max drawdown (equal 1R per trade).

## 7. Known limitations (accepted)

1. **Correlation:** SPX, US30 and NAS100 move together; oversold days are often shared. Extra trades may add risk
   concentration more than diversification. Section 6 measures this.
2. **Holdout contamination:** the NAS100 2025-2026 holdout result (PF 4.9) is known, and the indices are highly
   correlated, so the SPX/US30 holdout is weaker independent evidence than a truly fresh window.
3. **UTC-day D1 bars** (same approximation as cycle 4B; Connors defined RSI(2) on US-session closes).
4. **Fill model:** mid prices + 0.5 pt (locked runner); real spread is handled only by the spread-cost check.

## 8. Deliverables

`scripts/build_c11_data.py`, `scripts/run_c11_rsi2_cross_index.py`, outputs in `out/c11/`
(`dev_report.csv`, `holdout_report.csv`, `overlap.json`, `trades_<symbol>_<window>.csv`, MCPT null files,
`run_manifest.json`).
