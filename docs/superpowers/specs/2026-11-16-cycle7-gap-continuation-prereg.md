# Cycle 7 — Gap-Continuation SPX D1 (pre-registration)

**Date:** 2026-11-16
**Branch:** `cycle7-gap-continuation-spx` (off `cycle6-spx-led-fx` HEAD `d07a2a0`).
**Role in ensemble plan:** candidate #3.
**Author:** Claude Code session on 2026-11-16.

## 1. Hypothesis

On SPX (USA500IDXUSD) daily RTH bars (09:30-16:00 ET), days with a sufficiently large open-gap continue in the gap direction through the RTH session. Cycle 3 Gap-Fade on NAS100 shelved at PF 0.94 with 62.9% WR fading, suggesting the opposite archetype (continuation) is the untested quadrant on US indices post-2020.

## 2. Instrument and data

- Symbol: `USA500IDXUSD`.
- Bars: D1 built from `data/bars_m1_paired/USA500IDXUSD/`, aggregated over RTH window [09:30, 16:00) ET. Builder: `scripts/build_d1_rth_spx.py`. Output: `data/bars_d1_rth/USA500IDXUSD/year=YYYY/data.parquet`.
- Dev slice: 2015-01-01 → 2023-12-31. ~2300 RTH days.
- Holdout slice (SEALED until gates pass): 2024-01-01 → 2026-10-18.

## 3. Signal

Let `prev_c = mid_c[T-1]`, `open_T = mid_o[T]`. Gap = `open_T / prev_c - 1`.

- **Long**: if `gap > gap_min` → enter long at `ask_o[T]` (buy at the ask).
- **Short**: if `gap < -gap_min` → enter short at `bid_o[T]` (sell at the bid).
- No entry if `|gap| < gap_min`.

Max one position per day. No overnight.

## 4. Risk

- Stop: `stop_R × ATR14`, where `ATR14` is the 14-day True Range (NY RTH) ending on `T-1` (prior-day lookback — causal). Stop in price units = `stop_R × ATR14`.
- Long stop: `entry - stop_R × ATR14`. Short stop: `entry + stop_R × ATR14`.
- Target: none. Exit at stop hit OR RTH close `T`.
- Intraday fills modeled on the NY-RTH D1 bar high/low in the position's adverse direction (worst-case, stop fills exactly at stop price).
- Per-trade R unit = `stop_R × ATR14 × lots × point_value`. Normalize per-trade PnL to R by dividing by R-unit.

## 5. Grid (locked before any backtest)

**Total: 36 configs = 4 × 3 × 3.**

| param | values |
|---|---|
| `gap_min` | 0.0015, 0.0025, 0.0040, 0.0060 |
| `stop_R` (× ATR14) | 0.5, 1.0, 1.5 |
| `direction` | `long_only`, `short_only`, `both` |

## 6. Pre-reg deviation note — data peek

**Before writing strategy code I ran a dev peek on mean intraday return conditioned on gap bucket** (2015-2023, mid-to-mid, no costs, no stops):

- gap > +0.40%: n=468, mean +11.77 bp, 63.5% positive.
- gap > +0.60%: n=267, mean +16.64 bp, 65.9% positive.
- gap < −0.40%: n=394, mean +0.49 bp, 53.0% positive.
- baseline drift all days: +1.97 bp, n=2335.

**Implication for pre-reg integrity.** Long-side continuation looks real; short-side looks dead. The grid still includes `short_only` and `both` because dropping them after the peek would be p-hacking. The peek is logged here as a researcher-degree-of-freedom.

## 7. Gate (pass conditions)

**Tier 1 — dev gate (per config).**
- PF ≥ 1.3.
- Trade count ≥ 150 over dev.
- Max drawdown ≤ 6R.
- Non-negative sharpe.

**Tier 2 — scheme-1 MCPT.** Reuse `v17.validation.c6_gates` + the MCPT infra on `cycle6-spx-led-fx`. Statistic: `mean_r`. 500 permutations. Dev p ≤ 0.05 AND holdout p ≤ 0.05 required.

**Tier 3 — paired-alpha.** 500 bootstraps. p_cum ≤ 0.01 (Bonferroni across 36 configs ⇒ per-config α = 0.05 / 36 ≈ 0.0014; use 0.01 as pragmatic Bonferroni-light tier with full 36-config correction in Tier 4).

**Tier 4 — Bonferroni.** For the ensemble framing, require any single surviving config's Tier 2 dev p ≤ 0.0014. If no config survives raw Bonferroni, treat the strategy as SHELVED regardless of Tier 1-3.

**Tier 5 — Holdout confirmation.** Winning config's holdout PF ≥ 1.2 and holdout MCPT p ≤ 0.05.

Failure at any tier ⇒ SHELVE. No rescue filter (per `feedback_prereg_discipline.md`).

## 8. Costs modeled

- Spread: ask-at-entry for long, bid-at-entry for short (already in RTH D1 bar schema).
- Slippage: 0 points additional (RTH open fills are typically clean on CFDs; optional sensitivity rerun at 1 pt later if base passes).
- Commission: 0 (FTMO index CFDs have zero commission; aligns with user's technical preference).

## 9. Non-goals

- No intraday TP, no trailing, no scale-out — single stop, EOD close.
- No calendar blackout — first-pass trades every day with a qualifying gap.
- No regime filter — adding one post-hoc after this spec = rescue filter = SHELVE.
- No FTMO account-level breaker simulation in the grid phase. Added only at ensemble-portfolio step.

## 10. Position sizing (for R accounting, not FTMO)

Fixed R-unit per trade. Lots sized so that `stop_R × ATR14 × lots × point_value = 1R`. PnL reported in R. No equity curve compounding at the grid phase.

## 11. Artifacts

- `scripts/run_c7_grid.py` — grid runner.
- `out/c7/dev_grid.csv` — per-config PF, sharpe, trades, max_dd, mean_r.
- `out/c7/dev_grid.log` — run log.
- Gate report after Tier 1 → `docs/superpowers/plans/c7_dev_gate_report.md`.

## 12. Timeline

- Grid run: single session (~30 min, 36 configs, D1 cheap).
- If Tier 1-3 pass: scheme-1 MCPT run (~1 session with permutation batching).
- Holdout run: sealed until Tier 4 passes.

## 13. Hard stop

If **zero configs pass Tier 1**, strategy is SHELVED same day. No param search beyond this grid.
