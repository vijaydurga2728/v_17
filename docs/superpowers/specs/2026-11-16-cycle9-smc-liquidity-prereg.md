# Cycle 9 — PDH/PDL Liquidity Sweep Reversal (frozen pre-registration)

**Date frozen:** 2026-11-16
**Branch:** `cycle9-smc-liquidity`
**Base commit:** `a5b2269` on `cycle8-donchian-trend`
**Phase 1 audit:** `docs/superpowers/specs/2026-11-16-cycle9-smc-liquidity-audit.md`
**Authorizing message:** user Phase 2 approval 2026-11-16.

This specification is the sole source of truth for cycle 9 behavior. Any deviation requires a written, timestamped ADR appended below §15 of this doc, with explicit user re-authorization.

---

## 1. Audit correction (user-flagged)

Audit §6 described its own table as "15 rows." The actual count is **17**. All 17 execution values are frozen below in §8. The audit doc should be read with this correction in mind.

## 2. Hypothesis (unmodified from user spec)

When NAS100 trades beyond the previous NY trading day's high (PDH) or low (PDL), then closes back inside that level on a completed M15 bar, subsequent price action may exhibit reversal behavior toward the opposite previous-day liquidity level.

No trend filter, no CHoCH, no FVG, no order blocks in the primary experiment. Those are separate hypotheses (not scoped here).

The experiment can establish whether this price pattern has predictive value. It cannot establish that market makers deliberately hunted stops.

## 3. Instrument

**Single instrument.** Symbol: `USATECHIDXUSD` (NAS100 CFD, FTMO USTEC-compatible).

Bars source: `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/{dev,holdout}/year=YYYY/month=MM/data.parquet`. Schema in audit §2. M1 paired bid/ask OHLC + volume. Do not modify the source.

## 4. Dev/holdout split (Q1 — option B APPROVED)

- **Dev:** `2015-01-01` 00:00 UTC → `2022-12-31` 23:59 UTC (8 years).
- **Holdout:** `2023-01-01` 00:00 UTC → `2026-11-16` 23:59 UTC (sealed).

Rationale: cycle 4B RSI2-NAS100 used 2023-2026 as part of its own dev or holdout; the researcher has partial knowledge of 2025-2026 broad regime through cycle 4B outcomes. Pulling cycle 9 holdout back to 2023 reduces cross-cycle contamination at the cost of 2 dev years.

**Holdout discipline:** no inspection of holdout performance during development, parameter tuning, or candidate selection. Holdout is touched exactly once per candidate, after all Tier 1-3 gates pass on dev.

## 5. Session calendar (Q2 — exclude half-days APPROVED)

- **Timezone:** `America/New_York` tz-aware conversion. Single source of truth for day-boundary.
- **Trading-day definition:** a NY trading day D is defined as the calendar date in `America/New_York` for which the full 09:30-16:00 ET RTH session is open.
- **Calendar source:** NYSE trading calendar via `pandas_market_calendars` (`XNYS`) if the library is available; else hand-rolled fixed list of US federal holidays and Good Friday. Lock the chosen source in the first Phase 3 code commit.
- **Half-day handling:** fully excluded. If NYSE lists D as a half-day (early close 13:00 ET; typically day after Thanksgiving, Christmas Eve when it falls on a weekday, Jul 3 when Jul 4 falls on a weekday), then:
  - D is **not** a valid signal day.
  - D's High and Low are **not** used as PDH/PDL for D+1.
  - Instead, D+1 uses the most-recent **full** RTH day's High/Low as PDH/PDL.
- **DST:** handled implicitly by tz-aware conversion. Document the fact that M15 session bins remain fixed at 09:30, 09:45, ..., 15:45 in America/New_York local time; the UTC timestamps shift by 1h across DST boundaries and this is correct behavior.
- **First signal day:** day D must have a well-defined PDH/PDL from a prior **full** RTH day. First dev signal eligible: the first full RTH day after 2015-01-02.

## 6. M15 bar construction (deterministic)

Bars are built on-the-fly from M1 paired source via session-aligned resample, not persisted to disk as a new dataset. Rules:

- Window: `[09:30:00, 16:00:00) America/New_York`. Each RTH session yields 26 M15 bins (09:30, 09:45, ..., 15:45).
- Bin assignment: an M1 bar `t` belongs to the M15 bin `t.floor_to_15_min_local`.
- M15 bar OHLCV (bid side, symmetrically ask side):
  - `bid_o` = first M1 `bid_o` in bin by `ts_utc`.
  - `bid_h` = max M1 `bid_h` in bin.
  - `bid_l` = min M1 `bid_l` in bin.
  - `bid_c` = last M1 `bid_c` in bin by `ts_utc`.
  - Ditto for ask.
  - `mid_o/h/l/c` = `(bid + ask) / 2` for each.
  - `bid_volume = sum`, `ask_volume = sum`.
  - `n_m1_bars = count`.
- **Incomplete-bar rule:** exclude any M15 bin where `n_m1_bars < 5` (33% of 15). Protects against sparse early/late-session data.
- **Half-day bins:** since half-days are excluded wholesale (§5), their M15 bins never enter the signal path.

## 7. PDH/PDL levels

For each eligible NY trading day D:

- `PDH[D]` = max over the last **full** RTH day `D_prev` of `mid_h` across all M15 bins in `D_prev`.
- `PDL[D]` = min over `D_prev` of `mid_l`.
- `D_prev` is the most-recent full RTH day strictly before D (not the calendar-previous day).
- Levels `PDH[D]`, `PDL[D]` are fixed for the entire RTH session of D. No intraday recomputation.

## 8. Frozen execution model (all 17 rows)

| # | Item | Frozen value |
|---|---|---|
| 1 | ATR timeframe | M15 |
| 2 | ATR window | 14 completed M15 bars |
| 3 | ATR calculation | True Range = max(H−L, \|H−C_prev\|, \|L−C_prev\|) on M15 **mid** OHLC; Wilder-smoothed (α = 1/14) over 14 completed bars |
| 4 | ATR warmup | `atr14_m15_prev` defined only after 14 completed M15 bars have accumulated within the continuous dev stream; **ATR history is continuous across year/month parquet partitions** (concat dev into one time-ordered stream before smoothing) |
| 5 | ATR leakage prevention | Dev-only M15 stream builds dev ATR. Holdout M15 stream builds holdout ATR starting from holdout's first bar with fresh warmup — holdout ATR does NOT consume dev's final state |
| 6 | Sweep buffer values | 0.00, 0.05, 0.10 × `atr14_m15_prev` (3 values; part of grid) |
| 7 | Minimum R/R | No minimum (test what data gives) |
| 8 | Maximum holding period | Until stop hit, target hit, or 16:00 ET RTH close (flat), whichever first |
| 9 | Position sizing | Fixed 1R per trade. Lots implied; backtest reports PnL in R units. No dollar sizing at grid phase |
| 10 | Max simultaneous positions | 1 per symbol |
| 11 | Daily signal limit | Max 1 long + 1 short per NY trading day, independently. Once a side's signal fires that day, further signals on the same side are muted |
| 12 | Session restrictions | Entry only during 09:30-15:30 ET (last entry 30 min before close; final M15 bin 15:30 bar) |
| 13 | News restrictions | None in baseline |
| 14 | Gap handling | If the next bar opens past the stop (adverse gap), fill at next-bar open (worst case). Same for target: if next bar opens through target, fill at next-bar open (favorable); report separately |
| 15 | Same-bar stop + target ambiguity | **Stop assumed hit first.** No optimistic ordering |
| 16 | Spread | Long entry at `ask_o[k+1]`, long exit at `bid_*` (stop at `bid_l`; target at `bid_h`; EOD at `bid_c[last]`). Short entry at `bid_o[k+1]`, short exit at `ask_*` (stop at `ask_h`; target at `ask_l`; EOD at `ask_c[last]`) |
| 17 | Slippage | 0 points baseline. **Also run +1 NAS100 point slippage sensitivity unconditionally**, not gated on baseline profitability |
| — | Commission | 0 (FTMO CFD-style) [not a frozen-model axis; stated for completeness] |
| — | EOD open-position policy | Flat at `bid_c` (long) or `ask_c` (short) of the 15:45 M15 bar |

(The 17 rows are items #1 through #17. Commission and EOD lines are informational aliases of item #16 ("Spread" governs EOD prices) and the model's "flat EOD" invariant implicit in #8.)

## 9. Grid (locked — 12 slots)

**Exactly 3 × 2 × 2 = 12 slots.** No additional axes without new experiment registration.

| axis | values |
|---|---|
| `sweep_buffer` (× ATR14_M15_prev) | 0.00, 0.05, 0.10 |
| `direction` | long_only, short_only |
| `N_conf` (confirmation window in M15 bars) | 1, 2 |

**No `both` direction axis.** "Both" results, if requested, are post-hoc aggregation of `long_only` + `short_only` slot results, not a separate experiment.

## 10. Signal logic (deterministic rules)

### 10.1 Sweep detection

Scan M15 bars during RTH 09:30-15:30 ET, in order.

- **High sweep candidate at bar `k`**: `mid_h[k] > PDH[D] AND mid_c[k] < PDH[D]`.
- **Low sweep candidate at bar `k`**: `mid_l[k] < PDL[D] AND mid_c[k] > PDL[D]`.

Only the first qualifying high-sweep and the first qualifying low-sweep per day are considered (one per side per day).

### 10.2 Confirmation

Let `k` be the sweep bar. The sweep is **confirmed** if, within the next `N_conf` M15 bars (i.e., bars `k+1 .. k+N_conf` inclusive), there exists a bar `j` such that:

- **High sweep (short setup):** `mid_c[j] < mid_l[k]`. Candle closes below the sweep bar's low.
- **Low sweep (long setup):** `mid_c[j] > mid_h[k]`. Candle closes above the sweep bar's high.

If no bar in `[k+1, k+N_conf]` confirms, the sweep is invalidated for that side on that day. No entry.

Also invalidate if during `[k+1, k+N_conf]` the price **extends further** beyond the swept level:

- High sweep: if `mid_h[j] > mid_h[k]` for any `j` in the window before confirmation, invalidate. This prevents entry during a momentum breakout.
- Low sweep: if `mid_l[j] < mid_l[k]`, invalidate.

### 10.3 Entry

Entry is at the open of bar `j+1` (the bar after the confirmation bar), provided `j+1` is also within RTH 09:30-15:30 ET.

- Short: fill at `bid_o[j+1]`.
- Long: fill at `ask_o[j+1]`.

If `j+1 > 15:30` bar, invalidate (per §8 row 12).

### 10.4 Stop

At entry:

- Short: `stop = mid_h[k] + sweep_buffer × atr14_m15_prev[k]`.
- Long: `stop = mid_l[k] − sweep_buffer × atr14_m15_prev[k]`.

ATR is `atr14_m15_prev[k]` — the Wilder-smoothed ATR evaluated through bar `k−1` only, no look-ahead.

### 10.5 Target

- Short: `target = PDL[D]`.
- Long: `target = PDH[D]`.

### 10.6 Fill priority per bar

For each bar after entry, in order:

1. If bar's adverse extreme reaches stop (short: `ask_h >= stop`; long: `bid_l <= stop`), exit at `stop` (stop-first rule §8 row 15).
2. Else if bar's favorable extreme reaches target (short: `ask_l <= target`; long: `bid_h >= target`), exit at `target`.
3. Else continue.
4. On the 15:45 M15 bar, after steps 1-2, if still open, exit flat at `bid_c[last]` (long) or `ask_c[last]` (short).

Adverse gap at bar open (row 14): if `bar.open` is already past the stop (for a short: `ask_o >= stop`; for a long: `bid_o <= stop`), fill at `ask_o` (short) or `bid_o` (long) — worst case.

### 10.7 R calculation

`R = (exit_px − entry_px) / stop_distance` for long. Inverse for short. `stop_distance = |stop − entry_px|` fixed at entry.

### 10.8 Reward/risk feasibility

If at signal time `target_distance / stop_distance < 0.5`, the trade is still taken (per §8 row 7: no min R/R). But the trade is logged with a `rr_at_entry` field so post-hoc analysis can slice on this.

## 11. Duplicate-signal and invalidation rules

- One long signal max per NY trading day. Once fired, additional low-sweeps that day → ignored.
- One short signal max per NY trading day. Symmetric.
- Long and short on the same day are independent (per §8 row 11).
- Within the per-side count, only the first confirmed sweep counts. A sweep that invalidates (§10.2) does not consume the daily quota.

## 12. Validation gates (Tier 1 → Tier 4)

**Tier 1 — dev gate per slot** (12 slots):

- PF ≥ 1.3.
- Trade count ≥ 100 over 8 dev years (~12.5/yr minimum).
- Max drawdown ≤ 8R.
- Sharpe ≥ 0.

**No loosening of Tier 1 permitted without a written ADR and user re-authorization.**

**Tier 2 — scheme-1 MCPT, run immediately after Tier 1 pass per slot:**

- Null: block-bootstrap of M15 mid log-returns. Block size = 26 (one full RTH session), 500 permutations, seed logged.
- Statistic: observed `mean_r`.
- p-value: fraction of null `mean_r` ≥ observed, +1 smoothing.
- **Threshold:** p ≤ 0.05 at this tier (per-slot uncorrected).

Rationale for block size 26: one trading session is the natural dependence unit. Block=10 (cycle 8 choice) is M15-inappropriate; 26 preserves full-session autocorrelation.

**Tier 3 — ensemble-wide Bonferroni correction (Q5 APPROVED):**

Family-wise α = 0.05.
Total slots across cycles 6-9 ensemble plan = **132** (cycle 6: 48, cycle 7: 36, cycle 8: 36, cycle 9: 12).
Per-slot corrected threshold:

```
α_corrected = 0.05 / 132 = 0.0003787879
```

Tier 3 requires Tier 2 p-value ≤ 0.0003787879. **Do not relax.**

**Tier 4 — holdout confirmation:**

For each slot that passes Tier 3, run on holdout (2023-01-01 → 2026-11-16) with holdout-only ATR stream (§8 row 5). Gates:

- Holdout PF ≥ 1.2.
- Holdout MCPT p ≤ 0.05 (scheme-1 same methodology, holdout-only block bootstrap).
- Holdout touched exactly once per slot. No re-inspection.

**Tier 5 — slippage sensitivity (Q3 unconditional):**

Rerun Tier 1-4 with `slippage = +1` NAS100 point applied adversely at every fill (long entry: ask + 1; short entry: bid − 1; stop and target fills offset adversely). Run **independently of baseline outcome** per Q3 APPROVED. Report side-by-side baseline vs +1pt.

**Candidate acceptance decision:**

A slot is **accepted** only if it passes Tier 1 AND Tier 2 AND Tier 3 AND Tier 4 on baseline AND Tier 4 on +1pt slippage.

A slot is **rejected (SHELVED)** on any gate failure. No parameter rescue.

## 13. Analysis dimensions (required, after decisions above complete)

After acceptance/rejection decisions are locked, produce an analysis report covering, per slot (both passing and failing):

- Profit factor.
- Mean R per trade.
- Win rate.
- Max drawdown.
- Trade count.
- Long vs short performance decomposition.
- Trend-day vs range-day performance (trend-day classifier: `|close − open| / (high − low) > 0.7` for the full-day RTH; explicitly a post-hoc tag, **not** a filter).
- High-volatility vs low-volatility performance (daily ATR percentile).
- Yearly PnL.
- Pre-2018 vs post-2018.
- Post-2020 only.
- Zero-slippage vs +1pt slippage.
- `rr_at_entry` distribution and sliced returns by R/R bucket.

The analysis is observational, not basis for re-parameterizing. Pattern found here may inform a NEW experiment (new pre-reg, new branch), never this one.

## 14. Deliverables (Phase 3-6 scope)

Code paths (all new; no modification of existing strategies/validators):

- `scripts/build_m15_rth_nas.py` — on-demand M15 session-aligned resampler (or in-memory helper inside `src/v17/setups/c9_pdh_pdl.py`). May persist to `data/bars_m15_rth/USATECHIDXUSD/` for reproducibility.
- `src/v17/setups/c9_pdh_pdl.py` — deterministic rule implementation (sweep detection, confirmation, entry, stop, target, R).
- `src/v17/backtest/c9_runner.py` — per-slot runner.
- `src/v17/backtest/c9_grid.py` — 12-slot grid driver.
- `src/v17/validation/c9_mcpt.py` — scheme-1 block-bootstrap MCPT with block size 26.
- `tests/unit/c9/` — unit tests for (a) half-day exclusion, (b) PDH/PDL computation (property: PDH ≥ PDL, PDH[D] ∈ prior-day close ± daily range), (c) sweep detection boundary cases, (d) same-bar stop+target ordering, (e) adverse-gap fill, (f) ATR warmup absence of look-ahead.
- `tests/integration/c9/` — single-fold smoke test on one dev month.
- `out/c9/grid_report.csv`, `out/c9/mcpt_report.csv`, `out/c9/holdout_report.csv`, `out/c9/slippage_sensitivity.csv`.
- Reports under `docs/superpowers/plans/c9_*`.

## 15. Deviations, ambiguities, and unresolved items

1. **Holdout partial contamination** (§4): researcher partial knowledge of 2025-2026 regime through cycle 4B. User chose option B to mitigate; residual is accepted as "weak informed-researcher bias," formally logged here. No mitigation beyond option B.

2. **NYSE calendar source** (§5): final choice between `pandas_market_calendars` and hand-rolled deferred to first Phase 3 code commit. Both are deterministic.

3. **Ensemble-wide multiple-testing denominator** (§12 Tier 3): fixed at 132. If future cycles add more slots, cycle 9's threshold **does not retroactively tighten**. Tighter cycles pay their own Bonferroni.

4. **Volume data unreliable pre-2017** (audit §2): not used in this experiment. Mentioned for completeness.

5. **Flat-EOD at 15:45 M15 bar** means the official close is one bin before the 16:00 ET session end. Trades held past 15:45 are closed at the 15:45 bar's close. The `[15:45, 16:00)` interval of M1 bars is **not** traded — not entry-eligible, not exit-eligible. This is a deliberate conservative choice: protects against liquidity/wide-spread at the cash close.

## 16. ADR log (append-only; empty at freeze)

(No deviations recorded since freeze.)

---

**Freeze confirmed 2026-11-16.** No code changes until Phase 2 report is delivered and user acknowledges.
