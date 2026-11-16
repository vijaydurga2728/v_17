# Cycle 9 SMC Liquidity — Phase 1 Audit (repo + data)

**Date:** 2026-11-16
**Current branch:** `cycle8-donchian-trend` HEAD `a5b2269`.
**Working tree:** clean after cycles 6-8 commits.

## 1. Preservation targets (do NOT touch)

- Branch `ensemble-h1-cycle4` — RSI2-NAS100 cycle 4B production strategy.
- `scripts/demo_poll_mt5.py` — daily MT5 demo poll (runs 23:00 IST under Scheduler).
- `.env` with MT5 credentials for account `#53143050`.
- `out/demo/{equity_curve.jsonl, state.json, last_poll.txt}` — live demo log.
- Existing strategy code `src/v17/setups/`, validation `src/v17/validation/`, backtest `src/v17/backtest/c4*.py`, `c6*.py`.

## 2. Cycle-1 NAS data provenance

### Path
`.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/{partition}/year=YYYY/month=MM/data.parquet`

### Partition layout
- `dev/year=2015..2024/month=01..12/` (10 dev years).
- `holdout/year=2025..2026/`.

### Schema (M1 paired, bid+ask OHLC + volume)
```
ts_utc        int64 (ns UTC)
symbol        string
bid_o/h/l/c   float64
ask_o/h/l/c   float64
bid_volume    float64
ask_volume    float64
spread_mid    float64
```

### Data quality check (sampled years 2015, 2020, 2023)

| year | rows | ts span (UTC) | median gap | max gap | gaps > 600s | duplicates | unique NY days |
|---|---|---|---|---|---|---|---|
| 2015 | 348,375 | 2015-01-01 01:00 → 2015-12-31 23:59 | 60s | 50h | 261 | 0 | 314 |
| 2020 | 345,705 | 2020-01-01 00:00 → 2020-12-31 21:14 | 60s | 77h | 259 | 0 | 313 |
| 2023 | 341,270 | 2023-01-02 23:00 → 2023-12-29 21:13 | 60s | 74h | 256 | 0 | 310 |

**Findings:**
- Bar frequency clean: median 60s confirms M1.
- Zero duplicate `ts_utc`.
- Max gaps correspond to weekends + public holidays. Expected for CFD.
- 310-314 unique NY calendar days/yr matches CFD running ~23h × 5d + weekend wicks. **RTH day count will be ~252** after session filter.
- Volumes non-zero from 2020 onward; older years have `bid_volume=0, ask_volume=0` — Dukascopy pre-2017 volume is unreliable. **Do not use volume in the primary experiment.**

### Holdout seal note (known cross-cycle contamination)

The same `holdout/year=2025..2026/` partition is the sealed holdout for **cycle 4B RSI2-NAS100**, which has already passed its holdout gate and is in 30-day demo. The researcher knows the 2025-2026 broad regime through cycle 4B results.

**Implication:** cycle 9's holdout is not fully blind. The strategy itself has not seen the data, but the researcher has partial knowledge of the regime. Log as a pre-reg deviation. Either (a) accept this weak contamination and proceed, (b) carve a smaller sub-period of 2026 for cycle-9-exclusive holdout, or (c) rebuild dev/holdout split on a different boundary (e.g., dev 2015-2022, holdout 2023-2026).

## 3. Dev/holdout split decision required (Phase 2 freeze)

Three options to lock before coding:

A. **Match cycle 4B.** Dev 2015-01-01 → 2024-12-31. Holdout 2025-01-01 → 2026-11-16. Holdout is pre-contaminated by researcher knowledge of cycle 4B outcomes.

B. **Shift split.** Dev 2015-01-01 → 2022-12-31. Holdout 2023-01-01 → 2026-11-16. Cleaner but loses 2 years of dev.

C. **Split 2026 only.** Dev 2015-01-01 → 2025-12-31. Holdout 2026-01-01 → 2026-11-16 (~10 months, ~210 RTH days). Honest blind holdout but small sample.

**Recommendation: B.** Cleanest with reasonable both-side samples. Need user sign-off.

## 4. M15 bars

**Not built.** Must resample from M1 paired. Session-aligned M15 bins (09:30, 09:45, 10:00, ...) — NOT UTC-midnight aligned.

Resample rule: for NY-RTH window [09:30, 16:00) ET, generate 26 M15 bars per RTH session. Out-of-session M1 bars excluded.

New script: `scripts/build_m15_rth_nas.py`. Output: `data/bars_m15_rth/USATECHIDXUSD/year=YYYY/data.parquet`.

## 5. Session calendar freeze requirements

Before any code:

- **Trading-day calendar:** NYSE calendar via Python `pandas_market_calendars` or hand-rolled from known US holidays. Covers full-day closes and half-days.
- **Half-day handling:** half-day sessions (e.g., Nov 24 2017, Nov 29 2019, etc., close at 13:00 ET). **Decision needed:** (a) include half-days as normal RTH days with truncated RTH, (b) exclude half-days entirely from PDH/PDL and signal generation.
  - Recommendation: exclude half-days entirely. Reduces ambiguity.
- **DST:** `America/New_York` tz-aware conversion handles DST automatically. `pd.DatetimeIndex.tz_convert('America/New_York')` is the single source of truth.
- **First-day problem:** first RTH day of dev has no "prior day RTH" → first signal day is day 2, 2015-01-05 (Monday, since 2015-01-02 was Friday).

## 6. Execution-model missing values (Phase 3 lock list)

Spec says these must be preregistered. Below is my proposal; user must accept, modify, or reject each.

| Item | Proposed value | Rationale |
|---|---|---|
| ATR window (M15) | 14 bars | Standard; 3.5h of intraday vol |
| ATR calculation | Wilder-smoothed true range on M15 bid-ask midpoint | Deterministic, no look-ahead |
| ATR warmup | Signals muted until `atr14_m15_prev` is non-null (first 14 M15 bars per dev) | — |
| Sweep buffer values | 0.00, 0.05, 0.10 × ATR14_M15_prev | Per your push-back |
| Minimum R/R | No minimum (test what the data gives) | Keeps hypothesis clean |
| Maximum holding period | Until target hit, stop hit, or 16:00 ET RTH close (whichever first) | Flat EOD |
| Position sizing | Fixed R per trade; lots = 1R ÷ (stop_distance × point_value) | Standard |
| Max simultaneous positions | 1 per symbol | No pyramiding |
| Daily signal limit | 1 long + 1 short max per day (independent sides) | User can also pick strict 1/day total |
| Session restrictions | Entry only during 09:30-15:30 ET (last entry 30 min before close) | Avoids near-close no-room entries |
| News restrictions | None in baseline | Per your push-back |
| Gap handling | If next-bar open gaps beyond stop, fill at next-bar open (adverse) | Conservative |
| Same-bar stop+target ambiguity | Assume stop hit first (adverse) | Conservative |
| Spread | Bid-at-fill short, ask-at-fill long (already in paired bars) | — |
| Slippage | 0 base; sensitivity rerun at +1 point only if base passes | — |
| Commission | 0 (FTMO CFD-style) | Matches user's broker preference |
| EOD open position | Flat at bid/ask close price of last RTH bar | — |

## 7. Multiple-testing ledger

Pre-reg grid = 3 sweep buffers × 2 directions (long_only, short_only) × 2 N_conf (1, 2) = 12 slots.

"Both" direction will be a post-hoc aggregation of long_only + short_only results — NOT a separate grid slot. Keeps slot count honest.

Bonferroni α per slot = 0.05 / 12 ≈ **0.00417**.

Running cross-cycle ledger entry (append to future `docs/superpowers/plans/GATE_MANIFEST.md`):
- Cycle 6: 48 slots. 0 passes.
- Cycle 7: 36 slots. 0 passes.
- Cycle 8: 36 slots. 0 passes.
- Cycle 9 (this): 12 slots proposed.
- **Ensemble-wide total: 132 slots so far.** Ensemble-wide Bonferroni if we insist on family-wise error control = 0.05 / 132 ≈ 0.00038. User-level decision whether to apply.

## 8. Phase 1 conclusion

Data is suitable for PDH/PDL sweep-reversal on NAS100 M15 with these caveats:
1. Holdout is weakly contaminated (section 2).
2. M15 bars must be built fresh with session-aligned bins (section 4).
3. Half-day handling must be explicitly decided (section 5).
4. Execution-model values must be user-approved (section 6).
5. 12-slot pre-reg grid is proposed; ensemble-wide Bonferroni is a user call (section 7).

## 9. Blocking questions for Phase 2 freeze (user sign-off required)

Q1. Dev/holdout split: option A, B (recommended), or C from §3?
Q2. Half-day handling: exclude, or include with truncated RTH?
Q3. Execution-model values in §6: accept all, or line-by-line override?
Q4. Daily signal limit: 1 long + 1 short per day, or strict 1 trade per day total?
Q5. Multiple-testing: apply cycle-level Bonferroni only (0.00417), or ensemble-wide (0.00038)?
Q6. Branch strategy: new branch `cycle9-smc-liquidity` off `main`, or off `cycle8-donchian-trend` HEAD to inherit infra?

No code written until Q1-Q6 answered.
