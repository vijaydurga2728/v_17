# ADR 001 — Cycle 9 Phase 2 corrections

**ADR id:** cycle9-adr-001
**Status:** ACCEPTED
**Date-authorized:** 2026-11-16
**Authorizing message:** user review of Phase 2 report, 2026-11-16.
**Supersedes-parts-of:** `docs/superpowers/specs/2026-11-16-cycle9-smc-liquidity-prereg.md` sections listed per correction below.
**Base commit:** `655543c` on `cycle9-smc-liquidity`.

This ADR is authoritative over any conflicting text in the original Phase 2 pre-registration. The original pre-reg §1–§15 remains unchanged on git record to preserve the Phase 2 history. §16 of the pre-reg carries a one-line pointer to this ADR.

## Correction A — MCPT permutation count and null-process specification (BLOCKING)

**Supersedes:** pre-reg §12 Tier 2.

**Problem.** Original Tier 2 specified 500 permutations with +1-smoothed p-value. Smallest achievable p = 1/(500+1) ≈ 0.001996. Tier 3 ensemble-wide Bonferroni threshold is α = 0.05/132 ≈ 0.0003788. With 500 perms **no slot can mathematically pass Tier 3**, independent of true edge.

**Resolution.**

1. **Permutation count:** 100,000 per slot that reaches Tier 2.
2. **p-value formula:** `p = (count(null_mean_r >= observed_mean_r) + 1) / (N_perms + 1)`. With `N_perms = 100_000`, minimum resolvable p ≈ 9.9999e-6. Adequate headroom for α = 3.7879e-4.
3. **Seed discipline:** base seed `20261116`. Per-slot seed = `base_seed * 1_000 + slot_index` where `slot_index` is the 0-based position of the slot in the deterministic iteration order `(sweep_buffer, direction, N_conf)` sorted lexicographically. Example: slot `(0.00, long_only, 1)` → `slot_index = 0` → seed `20261116000`; slot `(0.10, short_only, 2)` → `slot_index = 11` → seed `20261116011`.
4. **Permutation methodology (block bootstrap of M15 mid log-returns):**
   - Compute M15 mid-close series `mc[1..N]` over the dev window with session-aligned bins.
   - Log-returns `r[i] = log(mc[i+1]) − log(mc[i])` for `i = 1..N-1`.
   - **Block size:** 26 M15 bars = one full RTH session.
   - For each permutation `p` in `1..100_000`:
     - Draw `ceil((N-1)/26)` block-start indices uniformly at random with replacement over `[0, N-1-26]`.
     - Concatenate blocks to form `r_perm[]` of length `N-1`.
     - **Rebuild synthetic mid-close:** `mc_perm[1] = mc[1]`; `mc_perm[i+1] = mc_perm[i] * exp(r_perm[i])`.
     - **Rebuild synthetic OHLC bid/ask:** preserve per-bar geometry (spreads, bar ranges) by translation. For each M15 bar `i`:
       - `delta_i = mc_perm[i] - mc[i]`.
       - Add `delta_i` to each of `bid_o/h/l/c, ask_o/h/l/c, mid_o/h/l/c` for bar `i`. Spread and intrabar range are preserved exactly.
     - **Recompute PDH/PDL on synthetic path** per §7 of the pre-reg, using the same NYSE-full-day calendar (half-days remain excluded). Levels are functions of `mid_h, mid_l` which have been shifted.
     - **Recompute ATR** on synthetic path per the corrected ATR initialization in Correction E below. Warmup consumes the first 14 synthetic TRs; no history leak from the real path.
     - **Rerun the full strategy** (sweep detection §10.1, confirmation §10.2 as corrected in Correction C, entry §10.3, stop §10.4 with corrected ATR, target §10.5, fill priority Correction D, daily quota §11) on synthetic bars.
     - Record synthetic strategy's `mean_r` over its synthetic trades.
   - Null distribution `null_mean_r[1..100_000]` is the collection of per-permutation strategy outcomes.
5. **Statistic:** observed strategy `mean_r` over dev trades for that slot.
6. **Logging:** each permutation writes a row with seed, block_starts hash, n_trades_null, mean_r_null to `out/c9/mcpt_perms_<slot_id>.parquet`. Facilitates reproducibility audits.
7. **Tier 3 threshold unchanged:** p ≤ 0.0003787879. Do NOT relax.

**Compute budget note.** 12 slots × 100_000 perms × full-strategy rerun ≈ non-trivial. Must profile. If one slot's strategy rerun is 50ms, one slot's MCPT ≈ 5000s ≈ 83 min; 12 slots ≈ 17 h. Expect need to parallelize or vectorize the strategy before MCPT. Document the realized throughput in the eventual MCPT report.

## Correction B — EOD execution boundary (BLOCKING)

**Supersedes:** pre-reg §6 ("26 bins including [15:45, 16:00)"), §10.6 step 4, §15 item 5, §8 row 12.

**Problem.** Pre-reg §6 defined 26 M15 bins per session (last bin `[15:45, 16:00)`), but §15 item 5 said the `[15:45, 16:00)` interval is "not traded." §10.6 step 4 said close at "the 15:45 M15 bar" — ambiguous.

**Resolution.**

- The `[15:45, 16:00)` M15 bin is **excluded entirely** from signal generation, entry, confirmation, stop evaluation, target evaluation, and exit.
- Per RTH session **25 tradeable M15 bins** are used: `[09:30, 09:45), [09:45, 10:00), ..., [15:30, 15:45)`.
- **Last entry-eligible bar:** the `[15:30, 15:45)` bar. Entries can fill at its open (per §10.3 "entry at open of bar after confirmation bar") only if the confirmation bar was `[15:15, 15:30)` or earlier.
- **Last exit-eligible bar:** the `[15:30, 15:45)` bar. Any position still open at this bar's close is flattened at `bid_c[15:30 bar]` (long) or `ask_c[15:30 bar]` (short).
- Half-day sessions remain fully excluded per pre-reg §5 (no partial-day adjustment to the 15:30 cutoff).
- Update pre-reg §6 bin count to **25** and §12 "Session restrictions" row 12 to "Entry only during 09:30-15:30 ET; last tradable bin ends 15:45 ET."

## Correction C — Chronological sweep processing (BLOCKING ambiguity)

**Supersedes:** pre-reg §10.1 "only the first qualifying sweep per side per day is considered," pre-reg §10.2 and §11 taken together.

**Problem.** Pre-reg §10.1 said "only the first qualifying sweep per side per day"; §11 said "invalidated sweep does not consume the daily quota." These together are ambiguous: if the first candidate sweep invalidates, is the second candidate processed?

**Resolution.**

1. During RTH (within the 25 tradeable bins), scan bars in chronological order per §10.1 for sweep candidates (high-sweep or low-sweep).
2. For each candidate `k`:
   - Enter "candidate pending" state for that side.
   - Watch bars `k+1 .. k+N_conf`:
     - If a bar `j` in this window satisfies the confirmation rule (§10.2 close-back-inside, no extension invalidation — see Correction F below), the candidate is **confirmed**. Entry per §10.3 at `j+1` open.
     - If the window closes with no confirmation, candidate is **invalidated**. State resets; continue scanning for the next candidate on the same side.
3. Per-side daily quota is consumed ONLY by a **confirmed** sweep that produces an entry. Invalidated candidates do not consume quota.
4. Once a side's quota is consumed, further candidates on that side are ignored for the day.
5. Long and short quotas are independent.

## Correction D — Deterministic fill-priority ordering (BLOCKING ambiguity)

**Supersedes:** pre-reg §10.6 (reorders steps), pre-reg §8 row 14.

**Problem.** Pre-reg §10.6 defined intrabar stop-first ordering but did not explicitly state that opening gaps are evaluated before intrabar extremes. Favorable target-gap handling was also implicit rather than deterministic.

**Resolution.** For each bar after entry (going forward until exit):

**Step 1 — opening gap check (priority):**
- If adverse open-gap through stop: short with `ask_o >= stop`, or long with `bid_o <= stop` → fill at `ask_o` (short) or `bid_o` (long), exit reason `stop_gap`.
- Else if favorable open-gap through target: short with `ask_o <= target`, or long with `bid_o >= target` → fill at `ask_o` (short) or `bid_o` (long), exit reason `target_gap`.
- Else proceed to step 2.

**Step 2 — intrabar stop check:**
- Short: `ask_h >= stop` → exit at `stop`, reason `stop`.
- Long: `bid_l <= stop` → exit at `stop`, reason `stop`.

**Step 3 — intrabar target check:**
- Short: `ask_l <= target` → exit at `target`, reason `target`.
- Long: `bid_h >= target` → exit at `target`, reason `target`.

**Step 4 — if still open and bar is the final tradable bar (`[15:30, 15:45)` of RTH):**
- Flat at bar close, reason `eod`.

**Slippage application (applies to every fill, regardless of reason):**
- Long fill: effective_price = raw_fill_price + slippage_points.
- Short fill: effective_price = raw_fill_price − slippage_points.
- Baseline run: slippage_points = 0.
- Tier 5 sensitivity run: slippage_points = 1.

## Correction E — Wilder ATR initialization (ambiguity)

**Supersedes:** pre-reg §8 row 3 and row 4.

**Problem.** "Wilder-smoothed (α = 1/14)" without an initialization rule is ambiguous. Common implementations differ by seed choice.

**Resolution.**

1. **Seed:** `ATR[13] = mean(TR[0..13])` — arithmetic mean of the first 14 valid True Range observations.
2. **Recurrence:** for `k >= 14`: `ATR[k] = (ATR[k-1] * 13 + TR[k]) / 14`. Equivalent to Wilder recurrence with α = 1/14.
3. **Causal access:** when computing signals at M15 bar `k`, use `atr14_prev[k] = ATR[k-1]`. No look-ahead.
4. **Dev continuity:** ATR history is built on a concatenated, time-ordered dev M15 stream. No reset at parquet year/month partition boundaries.
5. **Holdout independence:** holdout M15 stream builds its OWN ATR history starting from the first holdout M15 bar; it does NOT consume dev's final ATR state. Holdout's first 14 TRs are used for holdout's seed. Signals in the first 14 holdout bars (before `atr14_prev` is non-null) are muted.

## Correction F — Remove extension-beyond-swept-level invalidation (SPEC CORRECTION)

**Supersedes:** pre-reg §10.2 final paragraph ("Also invalidate if during [k+1, k+N_conf] the price extends further beyond the swept level").

**Problem.** The extension-invalidation rule I added in the Phase 2 freeze was not part of the user's original hypothesis. Keeping it silently changes the experiment: it adds a "no momentum breakout mid-confirmation" filter.

**Resolution.** Remove the extension-invalidation clause. Invalidation of a sweep candidate is driven by **ONLY**:
- The confirmation window `[k+1, k+N_conf]` expiring with no bar `j` satisfying `mid_c[j] < mid_l[k]` (high sweep) or `mid_c[j] > mid_h[k]` (low sweep).

Extended moves beyond the swept level during the confirmation window do NOT by themselves invalidate the candidate. The candidate remains active until either a confirmation bar closes back inside or the window expires.

## Correction G — NYSE calendar dependency (precision)

**Supersedes:** pre-reg §5 ambiguity, §15 item 2.

**Resolution.**

- Use `pandas_market_calendars` package. Calendar: `XNYS`.
- **Pin exact version** in a `requirements.txt` or `pyproject.toml` lock entry. Choose the latest stable at Phase 3 code start; record the pinned version in a commit message and in `out/c9/env_pin.txt`.
- **No hand-rolled fallback.** If `pandas_market_calendars` is unavailable, Phase 3 fails and we re-plan. Determinism > robustness here.
- Full-day RTH = `market_open = 13:30 UTC` (DST-aware) and `market_close = 20:00 UTC`, mapping to `09:30 ET` and `16:00 ET` after DST. The library returns these correctly.
- A trading day D is treated as a **full day** iff `market_close − market_open == 6h30m` for D. Half-days (6h30m ≠ market duration) are fully excluded per pre-reg §5 / Correction B.

## Correction H — Slot denominator permanence (confirmation)

**Clarifies but does not supersede:** pre-reg §12 Tier 3, §15 item 3.

Cycle 9's Tier 3 Bonferroni denominator is **permanently 132**. If a future cycle (10, 11, ...) adds more slots, cycle 9's threshold does not retroactively tighten AND does not retroactively loosen. Each cycle pays its own Bonferroni at the time it is run.

## Decisions log

| Blocker from Phase 2 report | Decision |
|---|---|
| Phase 2 ack | Acknowledged, subject to corrections A-H |
| Commit auth | Granted for two Phase 2 docs only (commit `655543c`); ADR and audit files require their own commit auth |
| Calendar source | `pandas_market_calendars` XNYS, version pinned, no fallback |
| Trading-day definition | Full 09:30-16:00 RTH only; half-days fully excluded |
| Slot denominator | 132 permanent |
| Extension invalidation | Removed (Correction F) |

## Authoritative read order for implementors

To understand cycle 9 rules at this point in time:

1. Read `docs/superpowers/specs/2026-11-16-cycle9-smc-liquidity-prereg.md` sections 1-15.
2. Read this ADR (`2026-11-16-cycle9-adr-001-phase2-corrections.md`).
3. Where the ADR corrects a pre-reg section, the ADR wins.
4. Any further deviation requires a new ADR with its own user authorization.

## Execution boundary

- Commit this ADR + pre-reg §16 pointer + consistency audit.
- Deliver revised-spec consistency audit for user review.
- **DO NOT** start Phase 3 code.
- **DO NOT** run backtests.
- **DO NOT** touch holdout.
- **DO NOT** modify cycle 4B, demo, protected outputs.
