# Cycle 9 — Phase 3 implementation notes

**Date:** 2026-11-17 (rev 2, after Phase 3 review)
**Branch:** `cycle9-smc-liquidity` (base `6d99a4c`)
**Spec read order:** pre-reg §1-15 → ADR 001 → ADR 002 (rev 2, ACCEPTED).
**Scope:** code and deterministic tests only. No grid run, no MCPT run, no holdout access, no
strategy performance analysis.

## Review status (2026-11-17, final)

| Item | Status |
|---|---|
| IMPL-3, 4, 6, 8, 10, 11 | APPROVED (IMPL-3 as changed to `k + N_conf + 1`) |
| Numba environment | APPROVED (numba 0.67.0 / llvmlite 0.49.0 pinned, installed in `.venv`) |
| ADR 002 rev 2 (I, J, K, L) | ACCEPTED, with stated limitation of the session-independent null |
| Phase 3 commit | AUTHORIZED |
| Phase 4 | AUTHORIZED for dev only (2015-2022): Tier 1, Tier 2 MCPT (100,000 perms), Tier 3 |
| Holdout | SEALED: no reads, no Tier 4, no holdout MCPT |

## Code

| Path | Contents |
|---|---|
| `src/v17/setups/c9_pdh_pdl.py` | XNYS full-day calendar, session-aligned M15 builder, `Sessions`, PDH/PDL, Wilder ATR, entry eligibility, slot simulation |
| `src/v17/backtest/c9_runner.py` | M1 loader (dev reads 2015-2022 partitions only; holdout needs `allow_holdout=True`), duplicate audit, `prepare`, Tier 1 metrics and gate |
| `src/v17/backtest/c9_grid.py` | 12-slot driver |
| `src/v17/validation/c9_mcpt.py` | ADR 002 I session-block null; fixed 100,000-permutation plus-one p; per-permutation log; seeds |
| `scripts/bench_c9_mcpt.py` | Reproducible numba vs pure-Python benchmark (synthetic data only) |
| `scripts/c9_mcpt_calibration.py` | ADR 002 Appendix A simulation (no market data) |
| `tests/unit/c9/` | 48 tests |
| `tests/integration/c9/` | 1 test: one real dev month (2015-03), structural invariants only |

## Environment

- The project venv is created with `--system-site-packages`: numpy and pandas resolve from user-site,
  pyarrow from the base interpreter. Not changed here, because the live RSI2 demo uses the same venv.
  Recommended follow-up: rebuild an isolated venv from a lock file after the demo window.
- `numba==0.67.0` and `llvmlite==0.49.0` are now installed **inside** `.venv` (verified by import path).
  `pandas_market_calendars==5.6.1` is also in `.venv`.
- Pins: `pyproject.toml` extra `c9`, `requirements-c9.txt`. Full resolved versions, paths and
  `pip freeze`: `out/c9/env_pin.txt`.

## Measured throughput (project venv, `scripts/bench_c9_mcpt.py 200`)

Synthetic random-walk data shaped like dev (2,000 sessions × 25 bins), slot `buf0.05_long_only_n2`:

| Path | ms per permutation | 100,000 permutations |
|---|---|---|
| numba 0.67.0 | 6.16 | 0.17 h per slot |
| pure Python | 56.49 | 1.57 h per slot |

Output saved to `out/c9/bench_mcpt.txt`. `test_numba_matches_pure_python` asserts identical results
on all 12 slots.

## Dev data integrity audit (2026-11-17; no strategy run)

Over the cycle 9 dev window (2015-01-01 to 2022-12-31): 2,773,351 M1 rows. 0 rows share a timestamp
(0 exact duplicates, 0 conflicts). 1,999 XNYS full days, all with data. 0 sessions missing the final
bin. 0 sessions with fewer than 25 bins. Items IMPL-1, IMPL-8 and IMPL-10 therefore change no dev
trade. They still guard the holdout and future data, which have not been audited (holdout sealed).

## Interpretations [IMPL-n]

Items marked **(behaviour)** can change which trades occur.

1. **[IMPL-1] Missing previous day.** PDH/PDL for D need the calendar-previous full RTH day. If that
   day has no bars, D gets no levels and no trades. A data gap never substitutes an older day.
2. **[IMPL-2] ATR seed.** TR needs a previous close, so the first valid TR is stream bar 1.
   `ATR[14] = mean(TR[1..14])`, and `atr_prev` is first defined at stream bar 15 (ADR 001 E).
3. **[IMPL-3] Scan resume (behaviour) — DECIDED 2026-11-17.** When candidate `k`'s confirmation
   window expires, scanning resumes at `k + N_conf + 1`. Bars inside the expired window are never
   re-scanned. The first later confirmed candidate consumes the daily quota.
   Tests: `test_bars_inside_expired_window_are_not_rescanned`, `test_scan_resumes_right_after_expired_window`.
4. **[IMPL-4] Entry bar is checked for exits (behaviour) — APPROVED.** The ADR 001 D steps (gap,
   stop, target, EOD) apply from the entry bar onward.
5. **[IMPL-5] Degenerate trades.** A trade with `stop_distance <= 0` is skipped (R undefined).
6. **[IMPL-6] PDH/PDL from 25 bins (behaviour) — APPROVED.** Levels use `[09:30, 15:45)` only.
   Observed and null are built identically.
7. **[IMPL-7] Slippage sign.** Buy fills +slip, sell fills −slip: adverse on every fill.
8. **[IMPL-8] Missing final bin (behaviour) — APPROVED 2026-11-17.** A session whose
   final tradable bin `[15:30, 15:45)` is absent (dropped by the n<5 rule) is **not entry-eligible**:
   no trade can open that day. This keeps the pre-registered EOD exit (close of the 15:30 bin) defined
   for every trade, instead of inventing a substitute exit. The session still supplies PDH/PDL for the
   next day. Rev 1 exited at the last existing bar instead. Dev impact: none (0 such sessions).
   Tests: `test_session_without_final_bin_is_not_entry_eligible`,
   `test_ineligible_day_still_supplies_levels_to_next_day`.
9. **[IMPL-9] Confirmation on the last bar.** No entry bar exists, so no trade. Quota not consumed.
10. **[IMPL-10] Duplicate M1 timestamps — CHANGED in rev 2.** Exact duplicate rows are dropped and
    counted. Rows that share a timestamp but differ raise `DataIntegrityError`. The audit dict
    (`rows_in`, `exact_duplicates_dropped`, `conflicting_timestamps`) is attached to the loaded frame
    as `attrs["c9_load_audit"]` and must be written to the Phase 4 data audit.
    Tests: `tests/unit/c9/test_c9_runner.py` (3 tests); the integration test asserts 0 conflicts.
11. **[IMPL-11] Sharpe — CHANGED in rev 2.** Per-trade `mean(R) / std(R, ddof=1)`. With zero
    dispersion (all R equal, or one trade) the value is `+inf`, `0` or `−inf` by the sign of mean(R),
    never NaN. Consequence: the Tier 1 gate "Sharpe ≥ 0" is exactly "mean(R) ≥ 0" in every case.
    Zero trades give NaN and fail. Tests: `test_zero_variance_sharpe` (4 cases),
    `test_tier1_sharpe_gate_equals_mean_sign`, `test_zero_trades_fail_tier1`.

## Tests run (rev 2)

See `test_run.log` in the review bundle. Totals and the full-suite result are in the hand-over message.

## Not done (boundaries)

- 12-slot dev grid not run. No MCPT run. No holdout read. No performance analysis.
- Phase 4 entry point (CLI writing `out/c9/*.csv` and the data audit) not written yet.
