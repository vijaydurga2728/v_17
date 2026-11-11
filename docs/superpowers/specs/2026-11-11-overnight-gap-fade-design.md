# Overnight Gap Fade — Design Spec (FROZEN)

**Status:** FROZEN 2026-11-11 before any code run.
**Branch of record:** `orb-reversal-indices` (ORB cycle SHELVED above this commit; gap-fade work continues on same branch).
**Prior cycles:** SB 6-engine SHELVED 2026-11-10; ORB-Reversal SHELVED 2026-11-11 (trend-filter rescue test honored pre-reg).

## 1. Hypothesis

Overnight gaps on US index futures/CFDs revert intraday a non-trivial fraction of the time. The published base rate for partial gap-close is strong (70-75% for small-to-medium gaps on cash-settled indices). Fade logic exploits the overnight-overreaction return pattern.

## 2. Strategy rules (LOCKED)

- **Instrument:** `USATECHIDXUSD` (NAS100). Single engine this cycle.
- **Gap definition:** `gap = open_09:30_NY - close_prev_16:00_NY` where "prev" is the prior trading day's cash-session close.
- **Gap size filter (apriori):**
  - Minimum |gap|/prev_close ≥ 0.30% (below = noise, skip).
  - Maximum |gap|/prev_close ≤ 2.00% (above = news event, do not fade).
- **Side:**
  - `gap > 0` (gap up) → short at open.
  - `gap < 0` (gap down) → long at open.
- **Entry:** market order at the 09:30 NY open bar's open price. Adverse slippage per `COST_SLIPPAGE_PTS` (0.5 pts USATECH).
- **Stop loss:** `sl = open - gap` (short) / `open + |gap|` (long). Interpretation: the stop is as far from entry as the gap size itself. 1R = |gap|.
- **Take profit:** `tp = open - 0.5 * gap` (short) / `open + 0.5 * |gap|` (long). Equivalent to a 0.5R target = 50% gap-close.
- **Time exit:** session close 16:00 NY (last cash-session M1 bar). TIME exit at session close if neither SL nor TP hit.
- **Max 1 trade/day/instrument.**
- **Cost model:** same as ORB — 0.5 pt slippage USATECH, 0 commission, bid/ask paired bars (entry at mid + slippage).

## 3. No-touch design (locked out of this cycle)

- No trend filter (overnight gap base rate is directional-agnostic in published literature).
- No ATR-based stop sizing.
- No VWAP trail.
- No volume filter.
- No day-of-week filter.
- No gap-size bin sub-strategies.

If this base-rule system passes G1-G5, MCPT follows. If it fails, SHELVE (one-shot, no rescue test this cycle).

## 4. Walk-forward

7 anchored folds, same `generate_folds()` schedule as ORB (OOS years 2018-2024).

## 5. Secondary gates (same thresholds as ORB except G2 relaxed-25)

| Gate | Threshold |
|---|---|
| G1 | PF ≥ 1.3 |
| G2 | trade_count ≥ 25 |
| G3 | every fold PnL (R) > 0 |
| G4 | R² ≥ 0.80 |
| G5 | cost-stress PF (2× slippage) ≥ 1.1 |

## 6. MCPT

If G1-G5 all pass: `run_mcpt(scheme="pnl_bootstrap", n_permutations=500, block_size=5)` on dev trades. α = 0.05. SHELVE if p-value > 0.05.

## 7. Honest expectation

- G1-G5 pass probability (base rule, single engine): 30-45%. Published base rate is better than ORB; naive entry is simpler, fewer failure modes.
- Pass + MCPT: 20-30%.
- Holdout survival: 50%.
- Compound DEPLOY: **10-20%**.
- End-to-end funded + first payout: **3-10%**.

Higher priors than ORB on paper, but same base-rate caveats apply. Three cycles in and the user has one documented SHELVE pattern — do not oversell this one.

## 8. Code scope

- Create `src/v17/setups/gap_constants.py`.
- Create `src/v17/setups/gap_engines.py` (one engine `GAP-NAS100`).
- Create `src/v17/setups/gap_fsm.py` (simpler than ORB — no OR window, just gap detection + entry).
- Add function in `src/v17/backtest/engine_runner.py` or new runner (gap entry is market not STOP; can reuse `simulate_fill_market`).
- `scripts/run_gap_dev_wf.py`, `scripts/run_gap_dev_gate.py`.

## 9. No scope creep

Any proposal to add parameters, filters, or sub-strategies after seeing results = cycle contamination. Enforce pre-reg: pass or SHELVE.
