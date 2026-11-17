# Cycle 9 — Revised-spec consistency audit

**Date:** 2026-11-16
**Scope:** Verify internal consistency of pre-reg (`2026-11-16-cycle9-smc-liquidity-prereg.md` §1-15) **as corrected by** ADR 001 (`2026-11-16-cycle9-adr-001-phase2-corrections.md`).
**Result:** 0 unresolved conflicts, 0 remaining ambiguities, 2 implementation-time items flagged for Phase 3 commit.

## 1. Methodology

For each pre-reg section, I inspected the authoritative text (pre-reg + ADR overrides) against every other section for logical conflict, undefined dependency, and ambiguous ordering. I also traced every row of the frozen execution table (§8) through §10's signal/exit flow to check for drift.

## 2. Pairwise consistency table

| Section pair | Issue checked | Status |
|---|---|---|
| §4 dev/holdout vs §8 row 5 ATR leakage | Holdout ATR must not consume dev state | OK — ADR E point 5 explicit |
| §5 half-day exclusion vs §7 PDH/PDL | PDH/PDL for D must come from most-recent full RTH day | OK — §7 says "most-recent full RTH day strictly before D" |
| §5 half-day vs §9 grid trade counting | Trade-count ≥ 100 must come from full-RTH days only | OK — half-days generate no signals, so no inflation possible |
| §6 M15 bins vs ADR B tradable bins | Pre-reg §6 said 26 bins; ADR B sets 25 tradable | **ADR B wins**, 25 tradable bins `[09:30..15:45)`. §6 geometry still describes 26 produced bins; one is filtered out of the signal path |
| §8 row 12 session restrictions vs ADR B | Entry window last bin should equal 15:30 bar | OK after ADR B rewrite |
| §8 row 14 gap handling vs §10.6 | Opening-gap check must precede intrabar extremes | **ADR D wins**, now step 1 opening gap, step 2-3 intrabar, step 4 EOD |
| §8 row 15 stop-first vs ADR D | Stop-first still enforced inside intrabar step | OK — ADR D step 2 before step 3 |
| §8 row 17 slippage vs §12 Tier 5 | +1pt sensitivity runs unconditionally | OK — pre-reg §12 Tier 5 explicit; ADR A does not touch this |
| §10.1 sweep candidate vs §10.2 confirmation window vs ADR F | No extension-invalidation | **ADR F wins** — extension clause removed |
| §10.1 "first qualifying sweep per side" vs §11 "invalidated does not consume quota" vs ADR C | Chronological scan, invalidated releases state | **ADR C wins** — now explicit |
| §10.3 entry at j+1 open vs ADR B last tradable bar | Entry cannot fall on `[15:45, 16:00)` | OK — pre-reg §10.3 already muted entries past 15:30 bar; ADR B tightens the definition of "past 15:30 bar" to mean "confirmation bar later than `[15:15, 15:30)`" |
| §10.4 stop uses atr14_prev[k] vs ADR E | ATR at bar k uses values up through k-1 | OK — ADR E point 3 explicit |
| §10.7 R formula vs §10.4 stop_distance | `R = (exit − entry) / stop_distance`; stop_distance fixed at entry | OK |
| §10.8 rr_at_entry vs no min R/R | Low-R/R trades still fire | OK — pre-reg §10.8 and §8 row 7 consistent |
| §12 Tier 1 gates vs §13 analysis dimensions | Trade count, PF, dd, sharpe are reported both at Tier 1 decision and in §13 analysis | OK |
| §12 Tier 2 perms vs ADR A | 100_000, block=26 | **ADR A wins** — 500 obsolete |
| §12 Tier 3 Bonferroni vs ADR A p-floor | Min achievable p ≈ 9.99e-6 < α = 3.79e-4 | OK — adequate resolution |
| §12 Tier 4 holdout vs §4 holdout window | Holdout single inspection, 2023-01-01..2026-11-16 | OK |
| §12 Tier 5 slippage vs ADR D step slippage | +1pt applied adversely to every fill regardless of reason | OK — ADR D explicit |
| §13 analysis dimensions vs §12 gates | Trend-day and vol-regime are **tags**, not **filters** | OK — explicit in §13 |
| §14 deliverables vs ADR dependencies | ADR calendar lib choice gates Phase 3 | OK — `pandas_market_calendars` XNYS |
| §15 item 2 NYSE calendar vs ADR G | Resolved to `pandas_market_calendars` with pin | **ADR G wins** |
| §15 item 5 EOD at 15:45 vs ADR B | Resolved: close at 15:30 bar's close | **ADR B wins** |

## 3. End-to-end signal trace (long side, worst-case day)

Test case: hypothetical NY trading day D with PDL = 17000.0. One M15 bar at `[10:30, 10:45)` dips to `mid_l = 16995`, closes `mid_c = 17003` (candidate low sweep, `mid_l < PDL AND mid_c > PDL`).

1. **Candidate detected at k=4** (bar index within RTH; `[10:30, 10:45)`).
2. **Confirmation window** `[k+1, k+N_conf]`. For N_conf=1: inspect only `[10:45, 11:00)`. For N_conf=2: inspect `[10:45, 11:00)` and `[11:00, 11:15)`.
3. Suppose bar j = k+1 = 5 (`[10:45, 11:00)`) closes `mid_c[j] = 17010 > mid_h[k] = 17008` → **confirmed**. (ADR F removal of extension-invalidation means we do NOT also check `mid_l[j] >= mid_l[k]` for extension.)
4. **Entry** at bar j+1 = 6 (`[11:00, 11:15)`) open: fill at `ask_o[6]`.
5. **Stop** = `mid_l[k] − sweep_buffer × atr14_m15_prev[k] = 16995 − 0.05 × atr14_prev[k]` (for sweep_buffer=0.05). ATR is `ATR[k-1]` per ADR E.
6. **Target** = PDH[D].
7. **Fill priority from bar 7 onward (ADR D order):**
   - Step 1: `bid_o[7] <= stop`? No → `bid_o[7] >= target`? No → continue.
   - Step 2: `bid_l[7] <= stop`? No → continue.
   - Step 3: `bid_h[7] >= target`? Yes → exit at `target`, reason `target`.
8. **R** = `(target − entry) / stop_distance` = positive.
9. **Daily quota**: long side consumed by this confirmed trade. Further low-sweeps on D are ignored. Short side unaffected.

No logic path hits an undefined rule. Trace closes cleanly.

## 4. MCPT null trace

Test case: one slot, one permutation.

1. Load dev M15 mid-close series `mc[]` with 25 bars/day × 8 years × ~252 days/year × 25 ≈ 50400 bars.
2. Compute log-returns `r[]` of length 50399.
3. Draw block starts per ADR A step 4. Block size = 26 (one full RTH session = 25 tradable + 1 excluded `[15:45, 16:00)` bar, or 25 bars if we match "tradable only"). **Flagged below** — see §5 item 1.
4. Concatenate block returns to length 50399 (truncate if over).
5. Build `mc_perm[]`, translate OHLC per ADR A step 4.
6. Recompute PDH/PDL on synthetic (half-day exclusion still applies based on calendar, not price).
7. Recompute ATR per ADR E; warmup consumes first 14 synthetic TRs.
8. Rerun full strategy §10 (as corrected) + fill priority §10.6 (ADR D) on synthetic bars.
9. Record synthetic mean_r.

Flagged ambiguity: block size "26" or "25"? (See §5 item 1 below.)

## 5. Implementation-time flagged items (not blocking spec freeze)

1. **MCPT block size 26 vs 25.** ADR A step 4 says "Block size: 26 M15 bars = one full RTH session." But ADR B establishes 25 tradable bins per session, with `[15:45, 16:00)` excluded. The log-return series is computed from tradable bars only (since `[15:45, 16:00)` is excluded from signal path and therefore from the synthetic rerun). Block size should match **25 bars** = one session of tradable bars. **Spec recommendation:** at Phase 3 code commit, interpret ADR A block size = **25**, not 26, and note this clarification in the first MCPT commit message. If user prefers 26 (including the excluded bin for pure returns-distribution purposes), file a new ADR. Default interpretation unless overridden: **25**.

2. **Calendar library version pin.** ADR G requires the exact `pandas_market_calendars` version pinned at Phase 3 code start. Pin and record in `out/c9/env_pin.txt` + `requirements-c9.txt` at the first code commit.

## 6. Consistency verdict

**Revised spec is internally consistent.** Pre-reg §1-15 + ADR 001 together form a unique, unambiguous rule set for implementation, subject to the two implementation-time clarifications in §5 (which have default resolutions).

No further ADR is required before Phase 3 authorization, unless user wishes to override §5 item 1 default (block size = 25).

## 7. Open user authorization requirements before Phase 3

1. Acknowledge this consistency audit.
2. Confirm or override §5 item 1 default (MCPT block size = 25 tradable bins). Default = 25.
3. Authorize commit of ADR 001 + pre-reg §16 pointer + this audit as a single commit on `cycle9-smc-liquidity`.
4. Authorize Phase 3 code start.

## 8. Preservation recheck

- `ensemble-h1-cycle4`: untouched.
- `scripts/demo_poll_mt5.py`: untouched.
- `.env`: untouched.
- `out/demo/*`: untouched.
- c6/c7/c8 commits: present in log.
- Cycle 9 base commit `a5b2269`: parent of current branch HEAD.
- Phase 2 original commit `655543c`: parent of the pending ADR commit.
