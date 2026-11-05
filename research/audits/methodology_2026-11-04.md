# Audit 3 — MCPT Methodology Review
**Date:** 2026-11-04
**Scope:** §13.1 methodology audit — six modules against spec §7
**Auditor:** test-engineer persona
**Status:** COMPLETE

---

## 1. Block Bootstrap block_size=5 (spec §7.1, L12)

**Finding: MEDIUM — Assumption unverified but acceptable under stated trade frequency.**

`mcpt_runner.py` line 14: `_BLOCK_SIZE = 5  # one trading week`.

Spec §7.1 states "block = 1 trading week." A trading week is 5 calendar days (Mon–Fri). If the trade series is indexed by **trade sequence number** (not by calendar date), then block_size=5 means "5 consecutive trades." This equals one trading week only when the engine fires exactly once per day.

The Silver Bullet engine fires at most once per session window per symbol per day. With 3 windows × 2–3 symbols, the daily trade count could be 2–9 trades. If it averages ~3 trades/day, 5 consecutive trades ≈ 1.6 days, not one week. The bootstrap then has weaker temporal autocorrelation capture than spec intends.

**However:** `block_bootstrap_pnl` shuffles trade-indexed P&L, not calendar-time P&L. The spec's intent is to preserve within-week autocorrelation in trade outcomes. At the actual OOS trade counts (expect 50–300 total across 7 folds per engine), the difference between block_size=5 and block_size=15 (3 trades/day × 5 days) is small relative to the already low power of a 1000-permutation bootstrap on a short series. No MUST_FIX, but should be documented as a known conservatism gap: the implemented block is shorter than the spec's calendar-week intent unless trades are ~1/day.

**Recommendation:** Add a comment in `mcpt_runner.py` documenting the assumption. Consider parameterising block_size per engine based on expected daily trade frequency when the trade series is known.

---

## 2. Scheme-1 config=None Passthrough (spec §7.1, R-02)

**Finding: HIGH — config=None disables Scheme 1; run_mcpt hard-codes config=None.**

`mcpt_runner.py` line 34:
```python
permuted_trades = permute_signal_time(trades, bars, config=None, seed=seed)
```

`permute_signal_time` with `config=None` returns `out = trades.copy()` — the original trades unchanged. Every permuted Scheme-1 stat is therefore identical to the observed stat. The resulting p-value is:

```
p_sharpe = fraction(permuted_sharpe >= observed_sharpe)
         = fraction(observed_sharpe >= observed_sharpe)   [all equal]
         = 1.0
```

A p-value of 1.0 means Scheme-1 **always fails** the gate. If the gate requires both schemes to pass, this silently kills every engine regardless of edge. If downstream code is written to pass on only one scheme (not both as spec §7.1 requires), Scheme-1 becomes a no-op sanity check that cannot reject anything, which is equally wrong.

Pre-flight ruling R-02 documents this as a known compromise ("timestamps preserved — used as sanity path"). The compromise is statistically unacceptable as a primary scheme. Scheme-1 as implemented does not test the null hypothesis stated in §7.1 ("a random entry during the SB window produces equivalent statistics"). It tests nothing.

**This is a MUST_FIX before the gate run.** Scheme-1 must receive a valid `SBEngineConfig` so the timestamp shuffle executes. The implementation in `permute_signal_time` is correct when config is provided — the fix is in the caller (`run_mcpt`), which must pass the engine's config object.

**Additional gap:** Even when config is wired up, `permute_signal_time` only reassigns `ts_entry_ns` in the trades DataFrame. It does not re-run the engine to recompute P&L under the permuted entry. `compute_stats` is then called on the trades DataFrame with the same `pnl_r` values but new timestamps. Sharpe and PF are computed from `pnl_r` which has not changed. The timestamps affect only time-bucketed stats if any. `compute_stats` does not use timestamps for Sharpe or PF — only `pnls` array. So **the P&L is not repermuted** under Scheme-1 even with a valid config. The null distribution is still identical to the observed distribution. The fix requires either (a) re-running the full engine on permuted entries (as spec §7.1 describes: "permuted engine then uses the same SL/TP rules against the real market data") or (b) acknowledging Scheme-1 reduces to timestamp-only reassignment with no P&L effect and treating it as a bookkeeping scheme only. Option (a) is the spec-compliant path and is a MUST_FIX.

---

## 3. Seed Determinism (spec §7.4)

**Finding: LOW — PASS. Deterministic across OS and Python version.**

`seeds.py` uses `hashlib.sha256` over a UTF-8 encoded string with `int.from_bytes(..., "big")`. SHA-256 output is byte-exact across OS and Python version. The `& 0x7FFFFFFFFFFFFFFF` mask ensures a non-negative 63-bit integer compatible with numpy's `default_rng`. No platform-dependent behaviour. PASS.

---

## 4. Bonferroni α Math (spec §7.3, L13)

**Finding: LOW — PASS with documentation note.**

Spec §7.3 states α = 0.05 / 6 = 0.00833. Spec §1 / L13 annotation notes "earlier conversational p < 0.0056 rounded for simplicity; exact Bonferroni is 0.00833." The methodology modules do not hard-code this threshold — `run_mcpt` returns raw p-values; threshold enforcement is deferred to downstream Task 8.1 scripts. This is architecturally correct (threshold is an evaluation concern, not a computation concern). No issue in these modules. The correct value is 0.00833.

---

## 5. Partition Guard (spec §6.1)

**Finding: LOW — PASS with one gap.**

`partition_guard.py` correctly raises `PartitionGuardError` unless `V17_HOLDOUT_UNSEAL=1`. The timestamp constant `HOLDOUT_START_UTC_NS = 1735689600000000000` decodes to 2025-01-01 00:00:00 UTC — matches spec §6.1 exactly.

**Gap:** `assert_dev_only` guards by partition label string, not by timestamp. A caller that passes `partition="dev"` but queries data timestamped after 2025-01-01 is not caught. `is_holdout_ts` exists but is not called inside `assert_dev_only`. Whether callers use both functions or only `assert_dev_only` determines the actual seal strength. No code path in these six modules calls the guard, so this is a cross-module concern. MEDIUM risk if the data layer relies solely on partition labels without timestamp cross-check.

**Recommendation:** Have `assert_dev_only` also reject if the timestamp range passed to it overlaps holdout, or document that callers must invoke `is_holdout_ts` separately.

---

## 6. compute_stats Edge Cases (spec §7.2)

**Finding: LOW — PASS with one gap.**

| Case | Behaviour | Verdict |
|---|---|---|
| Empty (`n=0`) | Returns all-zero StatsBundle | PASS |
| All-wins (`losses=0, wins>0`) | `pf = float("inf")` | PASS |
| All-wins (`losses=0, wins=0`) | `pf = 0.0` | PASS (zero trades net zero) |
| Zero std (`n=1` or constant P&L) | `std = 0.0` → `sharpe = 0.0` | PASS — ddof=1, n=1 guard |
| Single trade (`n=1`) | `std = 0.0` (ddof=1 fallback correct); `r2 = 0.0` (n>1 branch skipped) | PASS |
| Negative equity throughout | `peak = max.accumulate`, `dd = peak - equity` — works for all-negative equity (peak stays at first bar if that is highest) | PASS |

**Gap:** When `ss_tot == 0` (perfectly flat equity curve, e.g. all P&L=0), `r2 = 0.0` is returned, which is correct. However a flat-then-spike equity curve could yield `ss_tot > 0` with a negative R² if the linear fit is worse than the mean. Code does not clamp R² to [0, 1]. A negative R² is valid statistically but gate G4 (`r2 >= 0.80`) would still correctly fail — no functional bug, but downstream users should be aware R² can be negative.

Existing tests in `test_stats.py` cover empty, all-wins, linear equity, and max_dd. Missing: single-trade case and zero-std case as explicit tests. Not a gate blocker.

---

## 7. GateReport.all_pass Logic

**Finding: LOW — PASS.**

```python
@property
def all_pass(self) -> bool:
    return all([self.G1_pass, self.G2_pass, self.G3_pass, self.G4_pass, self.G5_pass])
```

All five gates are enumerated. No gate is omitted. `all([...])` returns False if any element is False, True only if all are True. Logic is correct. `test_secondary_gates.py` has a `test_passes_all_gates_on_strong_series` case that confirms the True path and a `test_fails_g5_when_cost_stress_pf_below_11` that confirms all_pass=False propagates. PASS.

---

## Summary Table

| # | Module | Finding | Severity | MUST_FIX |
|---|--------|---------|----------|----------|
| 2a | mcpt_runner.py | config=None hardcoded — Scheme-1 always returns unchanged trades → p=1.0 → gate always fails | HIGH | YES |
| 2b | mcpt_runner.py + mcpt.py | Even with config wired, pnl_r is not recomputed under permuted entry — Scheme-1 P&L null = observed | HIGH | YES |
| 1 | mcpt_runner.py | block_size=5 is ~1–2 trading days at realistic trade frequency, not 1 week | MEDIUM | NO |
| 5a | partition_guard.py | assert_dev_only guards by label only; timestamp cross-check not enforced inside the function | MEDIUM | NO |
| 6a | stats.py | R² not clamped to [0,1]; can be negative; no test for single-trade or zero-std | LOW | NO |
| 3 | seeds.py | SHA-256 deterministic across OS/Python — PASS | LOW | NO |
| 4 | mcpt_runner.py | Bonferroni threshold not in these modules (correctly deferred) — PASS | LOW | NO |
| 7 | secondary_gates.py | all_pass logic correct — PASS | LOW | NO |

---

## MUST_FIX Items (block gate run)

**MF-1 — Wire SBEngineConfig into run_mcpt Scheme-1 call.**
`mcpt_runner.py` must accept and pass the engine's `SBEngineConfig` to `permute_signal_time`. Without this, Scheme-1 is a no-op.

**MF-2 — Scheme-1 must trigger a full engine re-run, not just a timestamp relabel.**
Per spec §7.1: "permuted engine then uses the same SL/TP rules against the real market data." Reassigning `ts_entry_ns` in the trades DataFrame without re-running the event loop does not repermute P&L. `run_mcpt` for `scheme="signal_time"` must call the engine's backtest loop on each permuted entry set. This is the same architecture as the legacy `calculate_mcpt` function in `mcpt.py` — the pattern already exists; it must be applied here.
