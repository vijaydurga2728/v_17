# Candidate Decisions

**Date:** 2026-11-14
**Status:** Recommendation only. No candidate is pre-registered, implemented or backtested by this document.

## 1. Classification

| # | Candidate | Class | Reason |
|---|---|---|---|
| 7 | Market intraday momentum (Gao et al. 2018) | **A. Ready for pre-registration** | Peer-reviewed, independently confirmed in futures, fully mechanical, data on disk (US500/NAS100 M1; US30 raw). New family for v17. |
| 2 | Noise Area intraday momentum (Concretum) | **B. Needs additional evidence** | Gap-adjustment formula must be read from the paper (SSRN 4824172). No independent replication. Same family as #7. |
| 3 | EWMAC (Carver) | **B. Needs additional evidence** | Need FTMO overnight/weekend holding rules for the target account and a swap/financing cost model. Extension of the trend family already failed in 4B. |
| 1 | ORB stocks-in-play | **C. Needs additional data** (US stock universe + exchange volume) | The index version we *can* test is a different strategy, is already net zero in an independent CFD test, and mirrors our shelved ORB fade. Not worth buying data for an FTMO goal. |
| 4 | GEM | **D. Rejected** | Needs bonds/ex-US equity (outside user's universe). Independent work (ReSolve) says the original spec is luck. |
| 5 | IBS QQQ | **D. Rejected** | Author claim only; same dip-buy family as the live RSI2-NAS100 demo. |
| 6 | NR7 | **D. Rejected** | Ambiguous rules, hidden parameter, no evidence; long-only index drift overlaps RSI2. |
| 8 | RSI2 ES/NQ | **D. Rejected** | Parameter/filter adjustment of the live demo strategy. Adding a 200-day filter now = fifth p-hack layer. |
| 9 | ICT Silver Bullet | **D. Rejected** | Already tested and shelved (cycle 1). Undefined terms. |
| 10 | Market Profile 80% rule | **D. Rejected** | Discretionary last step; independent anecdote ~62%; reversion-to-value is the fade family that failed 3×. |
| 11 | IB iFVG | **D. Rejected** | Closed proprietary indicator. |

## 2. Selected for formal testing (max three)

Only **one family is new**. The three selections below are ranked; they are not three independent discoveries.

1. **Market intraday momentum on US500** (#7). Primary.
2. **Noise Area on US500** (#2). Same family as #1. Test only inside the same pre-reg as #1 with α split across both rules, and only after the gap formula is verified from the paper.
3. **EWMAC on the 9-instrument universe** (#3). Lowest priority. Counts as the trend family's second attempt (after 4B TSM/Donchian), not a new idea.

**Honest prior:** low. The intraday momentum edge is small (R² ~1–2%), and an independent CFD test of the closely related ORB found spread equal to the gross edge. My estimate for #1 surviving dev + holdout net of CFD spread: **10–20%**. I have not run anything to support this number; it is a judgement from the evidence above.

## 3. Recommended next experiment

**Step 0 — close cycle 6 first (pre-registered work in progress).**
- The dev grid has finished 28 of 48 configs; **all 28 have negative Sharpe** (range −1.31 to −1.01, ~5,800–6,300 trades each). `out/c6/dev_grid.csv` does not exist yet.
- Finish the 20 remaining configs exactly as pre-registered, run the dev gates, and fill ADR 0009. Expected outcome on current evidence: SHELVE.
- **Disclose in ADR 0009:** the uncommitted `c6_position.py` exit-variant hooks (`LEG_A_TARGET_R_MULT`, `TRAIL_FROM_ENTRY`), the `c6_grid.py` progress logging, and the root-level `diag_invert.py`, `diag_regime_invert.py`, `diag_variants.py`, `diag_v3_fulldev.py`, `diag_premise.py`. These are post-hoc explorations after seeing dev results. A signal inversion or exit-variant "rescue" is not in the pre-reg (spec §8.5 rescue requires a theory-grounded regime shift) and must not be adopted.

**Step 1 — Cycle 7 pre-registration (only after Step 0).** Single family: intraday index momentum.
- Instrument: `USA500IDXUSD`, cash session 09:30–16:00 America/New_York, mid price, Dukascopy bid/ask spread charged. Substitution SPY → US500 CFD stated in the spec.
- Rule frozen from Gao et al. 2018: sign of return from previous cash close to 10:00 ET; enter at 15:30 ET in that direction; exit at 16:00 ET close. No parameters to tune.
- Split: dev 2015-01-01 → 2023-12-31; holdout 2024-01-01 → 2026-10-14 (same as cycle 6, still sealed).
- Confirmation series: `USA30IDXUSD` (never touched). NAS100 as secondary (D1 holdout already opened, regime known).
- Report gross and net, plus a random-direction benchmark on the same timestamps (Krueger method) and scheme-1 MCPT.
- FTMO translation: fixed stop (e.g. ATR-based) chosen **from theory before running**, 0.5% risk; written into the pre-reg.
- Optional second rule (#2 Noise Area) only if the paper's gap formula has been read; α = 0.05 / 2.

**Step 2 — EWMAC only if Step 1 shelves and the user still wants another cycle.** Before freezing: confirm FTMO holding rules, build swap model, build US500/US30 D1.

## 4. Historical research recovery (Step 5 of the brief)

### 4.1 Cycle 4 H1 numbers (recovered from commit messages, smoke only; no formal gate report was written)

| Pair | Trades | PF | WR | Folds negative | Source |
|---|---|---|---|---|---|
| TSM-EURUSD H1 | 364 | 0.862 | 24.7% | 4/7 | `e57c370` |
| DON-EURUSD H1 | 1,697 | 0.874 | 36.8% | 5/7 | `57c9345` |
| DON-GBPUSD H1 | 1,681 | 0.955 | 38.5% | 4/7 | `57c9345` |
| DON-USATECHIDXUSD H1 | 1,637 | 1.209 | 41.8% | 1/7 | `57c9345` |
| RSI2-EURUSD H1 (symmetric) | 5,358 | 1.000 | 60.8% | 2/7 | `0fd08df` |
| RSI2-GBPUSD H1 (symmetric) | 5,341 | 1.028 | 61.6% | 3/7 | `0fd08df` |

The spec froze 8 pairs; TSM was smoked on EURUSD only. All failed G1 (PF ≥ 1.3). These results were seen before the 4B parameters were chosen (acknowledged in the 4B pre-reg §1).

### 4.2 RSI2-NAS100 pre-registration deviations

Memory recorded 4 layers. The documents show **6**:

1. Cycle 4 → 4B re-tune after seeing dev failures (`2026-11-11-cycle4b-correction-prereg.md` §1).
2. 4B formal gates: RSI2 failed G3 and per-pair MCPT (p_pf 0.610 vs α 0.00714). Gate report says "Pairs advancing to holdout: NONE" (`c4b_gate_report_2026-11-11.md`). Advanced anyway as "gate-limited" (`2026-11-11-cycle4b-mcpt-scheme-addendum.md` §4).
3. 4B pre-reg §7 binding SHELVE rule ("fewer than 2 pairs pass … SHELVES PERMANENTLY") was not applied: 0 pairs passed.
4. Scheme-1 MCPT with the pre-registered PF statistic failed: dev p_pf 0.114, holdout p_pf 0.148 (commit `9820638`). Addendum §5 required p_pf < 0.05.
5. Test statistic swapped PF → mean pnl_r after that failure; passed p = 0.002 (commit `05306bb`).
6. Paired-alpha "independent confirmation" designed after the fail (commit `ace826c`).

Also: demo length 90 → 30 days (recorded in user goals memory).

### 4.3 Existing MCPT and gate thresholds (read only, unchanged)

| Where | Threshold |
|---|---|
| Secondary gates G1–G5 (cycles 2–4B) | PF ≥ 1.3; trades ≥ 25; all folds net-positive; R² ≥ 0.80; 2× slippage PF ≥ 1.1 |
| Cycle 4B per-pair MCPT | Bonferroni α = 0.05 / 7 = 0.00714, scheme `pnl_bootstrap` (structurally unable to reject, per addendum §2) |
| Cycle 4B live-money gate | scheme-1 p_pf < 0.05, single pair |
| Cycle 4B holdout | PF ≥ 1.3, WR ≥ 50%, max DD < 10R, no FTMO hard-freeze |
| `src/v17/validation/thresholds.py` (M6 original) | min_pf 1.8, min_sharpe 2.0, max_dd 6%, min_winrate 0.50, MC p5 PF ≥ 1.3, MC p95 DD ≤ 8%, OOS trades ≥ 200, folds passed ≥ 4. **Not used by cycles 2–4B.** |
| Cycle 6 | D1–D6, A1–A3, H1–H5 in `src/v17/validation/c6_gates.py` (holdout Sharpe ≥ 0.7 × dev Sharpe per ADR 0009 template) |

### 4.4 Multiple-testing ledger (approximate count)

| Cycle | Evaluations seen |
|---|---|
| 1 SB | 1 engine run (6 specified) |
| 2 ORB | 2 (naked + filter rescue) |
| 3 Gap | 1 |
| 4 H1 | 6 smoked pairs |
| 4B | 7 formal pairs + 3 RSI2 re-tests (scheme-1 PF, mean_r, paired) + GBPUSD scheme-1 + 16 pooled FX p-values |
| 5 | 28 pairs full-window + 28 rolling |
| 6 | 28 of 48 grid configs so far + ≥5 post-hoc diag scripts |
| **Total** | **~130 evaluations across ~9 strategy families** |

Practical meaning: any new "pass" at α = 0.05 is expected by chance roughly once per 20 evaluations. A new cycle should be judged against a sealed holdout plus an untouched confirmation series (US30), not dev p-values alone.

### 4.5 Cycle 6 unfinished dev grid

- Progress file: `out/c6/dev_grid.progress` (run started 2026-11-13 14:38, stopped after config 28 at 16:39).
- 28/28 completed configs have Sharpe < 0; best K=0.4, sw=8, C=0.5, Sharpe −1.013, 5,854 trades.
- Remaining: 20 configs (K=0.4 sw≥12, all K=0.5). `run_grid` writes CSV only at the end.
- Nothing was modified by this audit.

## 5. What this audit did NOT do

- Did not open any primary PDF (SSRN, JFE). Several numbers are second-hand and marked.
- Did not verify broker symbols on the IC Markets terminal or FTMO, to avoid touching the running demo.
- Did not run any backtest, inspect any holdout, or change any code, threshold, contract or demo file.
