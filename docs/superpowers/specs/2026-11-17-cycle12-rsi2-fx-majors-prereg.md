# Cycle 12 — RSI(2) on the 7 FX majors (pre-registration)

**Status:** FROZEN 2026-11-17 on user request "test this strategy for forex major pairs". Committed before any
cycle 12 code or result.
**Branch:** `cycle12-rsi2-fx-majors` (from `8e119f6`).

## 1. Hypothesis

Connors RSI(2) mean reversion has an edge on FX majors. Two variants are pre-registered:
- **L (long-only):** exactly the NAS100 cycle 4B rule.
- **S (symmetric):** long when RSI(2) < 10, short when RSI(2) > 90. FX has no structural upward drift, so a
  long-only rule has no a-priori reason to be preferred (lesson recorded 2026-11-11).

Pairs: EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD. **14 slots** (7 pairs × 2 variants).

## 2. Rules (per pair, one position at a time)

- RSI(2) Wilder and SMA(5) on D1 **mid** close, using the cycle 4B functions `_rsi_wilder`, `_sma`.
- Long: signal bar close RSI(2) < 10 → enter at next bar open. Exit at the close of the first bar (from the entry
  bar on) with close > SMA(5); else at the close of entry bar + 10 (TIME_CAP 10). Cycle 4B exit logic.
- Short (variant S): RSI(2) > 90 → enter at next open; exit at first close < SMA(5); same time cap.
- After an exit, scanning resumes at the bar after the exit bar (no entry on the exit bar), as in cycle 4B.
- If both conditions could apply on one bar (impossible: RSI < 10 and > 90), n/a.
- **Fills use real bid/ask:** long entry `ask_o`, long exit `bid_c`; short entry `bid_o`, short exit `ask_c`.
  No extra slippage. (The cycle 4B runner's 0.5-point slippage is in NAS100 index points and is meaningless
  for FX.)
- **R unit:** 1% of the signal bar's mid close (cycle 4B convention). `R = pnl / R unit`, sign by side.

**Parity check (required):** with fills switched to "mid open + 0.5, exit mid close" and long-only, the cycle 12
engine must reproduce `rsi2_runner.run_rsi2_oos_batch` trade by trade on the same bars.

## 3. Data and daily bars

- Paired M1 from `.worktrees/sb-6-engine-gate/data/bars/<PAIR>/{dev,holdout}/` (same source as cycle 4B).
- **D1 bars use the FX-standard 17:00 New York rollover:** a bar covers 17:00 ET (day − 1) to 17:00 ET (day),
  labelled with the closing day; weekend bars are not formed. This avoids the 2-hour Sunday "stub" bars that UTC-day
  bars contain (520 per pair in the existing cache). It also matches how MT5 brokers print FX daily bars.
- Bars are built fresh by the cycle 12 code (the existing `data/bars_d1` FX cache is not used; its EURUSD/GBPUSD
  files were rewritten 2026-11-11 and are under question).
- Bars are cached to `data/bars_d1_fxny/<PAIR>/` for reproducibility.

## 4. Windows

- **Dev:** signal bars from 2018-01-01 to 2024-12-31 (the cycle 4B walk-forward OOS years). Earlier data is used
  only for indicator warm-up. No parameters are fitted, so walk-forward folds reduce to calendar years; fold id =
  year of the entry bar (for G3).
- **Holdout:** signal bars from 2025-01-01 to the end of data. Run only for slots that pass dev.

## 5. Gates

**Dev (per slot)** — same standard as cycles 4B/11, computed with `evaluate_secondary`:
G1 PF ≥ 1.3; G2 trades ≥ 25; G4 R² ≥ 0.80; G5 cost-stress PF ≥ 1.1, where cost stress subtracts one extra
entry-bar spread (`ask_o − bid_o`) per trade. G3 (all years positive) reported, not gating.

**Luck test (gating):** random-entry null. Each permutation draws, without replacement from the eligible dev signal
bars, as many long entries as the slot has long trades and as many short entries as it has short trades, then applies
the same exit rules and fills. Statistic **mean R**. **10,000 permutations**,
`p = (count(null ≥ observed) + 1) / (10,001)`. **α = 0.05 / 14 = 0.003571.**
Seed: `20261117 * 1_000 + 200 + slot_index`, permutation `j` uses `default_rng([seed, j])`.
Slot order: pairs in the order listed in §1, variant L then S (`slot_index` 0..13).

**Holdout (dev passers only):** PF ≥ 1.3, win rate ≥ 50%, max drawdown < 10R, luck test p ≤ 0.003571
(holdout seed `+500`).

**Acceptance:** dev pass and holdout pass. Otherwise SHELVED, no changes.

## 6. Known limitations (accepted)

1. **Contamination:** on 2026-11-11 RSI(2) long-only was run informally on EURUSD and GBPUSD dev **and holdout**
   (UTC-day bars, NAS slippage model). The EURUSD and GBPUSD holdout is therefore not clean evidence for variant L.
2. **R unit** of 1% of price is large relative to FX daily ranges (~0.5-0.7%), so per-trade R values are small;
   gates on PF, R² and the luck test are scale-free, and max DD in R is reported in the same unit as NAS.
3. **Swap/financing costs** of holding FX positions overnight (1-10 days) are not modelled.

## 7. Deliverables

`src/v17/setups/c12_rsi2_fx.py`, `tests/unit/c12/`, `scripts/run_c12_rsi2_fx.py`; outputs in `out/c12/`
(`dev_report.csv`, `holdout_report.csv`, `trades/`, `mcpt/`, `run_manifest.json`, `data_audit.json`).
