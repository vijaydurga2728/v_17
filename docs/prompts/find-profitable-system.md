# Prompt: Find a profitable system for v17 (or prove none exists)

**Composed from** `MASTER_ANTIGRAVITY_WORKFLOW.md`:
- §0 Task Router — classification + no-false-claim rules
- §13 Research — primary-source edge candidates, no popularity bias
- §12 Performance Investigation — measurement discipline for every claim
- §3 Systematic Debugging — if a gate drops 100% of candidates, diagnose before deciding "no edge"
- §8 Security / Financial Integrity Audit — real-money deployment demands verified evidence

**Intended consumer:** a fresh engineering/research agent, zero v17 context.

**Critical constraint from the user who commissioned this prompt:**
> "I want a fully profitable system. Don't give me fake results. Don't tell me it's impossible — if that's your conclusion, you're missing a bug. Find and fix it ASAP."

This prompt must respect that goal *and* refuse to fabricate. Both at once. The agent cannot invent a positive result; the agent also cannot stop at the first failed gate without an evidence-ranked investigation of why.

---

```text
Task: Produce a profitable, FTMO-$10k-Normal-deployable v17 strategy — OR produce an
evidence-ranked explanation of why none exists under current data and infrastructure.
"Impossible" is only a legitimate conclusion when it is DEMONSTRATED, not assumed.

Expected result: ONE of (A), (B), (C), (D), with the measured evidence that forces it:
  A. A specific setup configuration (parameters, filters, timeframe) that passes the
     full M6 gate on 2021–2024 EUR+GBP with lookahead-safe code and FTMO Normal
     cost model. Ready to paper-forward for 2 months pre-deployment.
  B. A specific setup REPLACEMENT (named candidate from the allowed-source list)
     implemented as a new `SetupEngine` subclass that passes M6 on the same data.
  C. A set of concrete architectural bugs discovered in the current code that, once
     fixed, change (A) or (B) from "fail" to "pass". Each bug named with file:line
     and a before/after test. If the fix fails to flip the gate, say so plainly.
  D. A rigorous proof that no single-setup configuration within v17's current
     interface (SetupEngine → RiskEngine → EventLoop) can clear M6 on this data,
     accompanied by (i) per-gate drop tables for at least 3 alternative setups, and
     (ii) the minimum data or interface changes that would be required to change
     the answer. "No profitable system found" is a VALID outcome; "it's impossible"
     without the drop tables is NOT valid.

Non-goals (what you MUST NOT produce):
  - A positive result that cannot be reproduced from committed code.
  - Metrics computed from fewer than the M6-required OOS sample.
  - A "pass" claim that disappears when spread is inflated 50% or 100%.
  - A conclusion of "shelve the goal" without the Outcome-D evidence above.
  - A revert of the lookahead-safe mitigation check (`z.mitigated_at <= now`).
  - A removal of the trade-level guards (dedupe, SL-side, fill-slip, post-fill RR).
  - A loosening of M6 thresholds to make the gate pass.
  - A claim of profitability that relies on fewer than 30 OOS trades per fold.

Classify per §0: this is simultaneously §13 (Research), §12 (Performance / measurement),
§3 (Bug fix if a canonical gate drops 100% of candidates), and §8 (Financial integrity —
real-money deployment).

PHASE 0 — reproduce the current baseline (1 h, read-only):
  - Confirm v17 state is what the user described: canonical ICT, lookahead-safe,
    trade-level bug fixes present, FTMO $10k Normal cost model, strict M6 thresholds.
  - Run `v17 backtest --symbol EURUSD --from 2021-01-01 --to 2024-12-31 --seed 42`.
  - Run same for GBPUSD.
  - Expected (per the delivering engineer's finding): 0 trades, 0 PF, 0 Sharpe.
    If you see different numbers, something has changed since the handoff — STOP and
    reconcile before continuing.

PHASE 1 — per-gate drop audit (2 h):
  - For each of EUR 2021, EUR 2024, GBP 2021, GBP 2024, run
    `scripts/diag_signal_audit.py <symbol> <year>-01-01 <year>-12-31`.
  - Produce one table per symbol-year: how many bars enter each gate, how many drop,
    where the chain terminates.
  - The gate that drops ≥ 95% of post-bias candidates is Gate X. Name it.
  - If Gate X is `_pick_zone` strict containment, Gate 1 candidate = relax containment
    to "price touched zone this bar" (bar range includes zone) rather than "price IS
    in zone at killzone-minute close". That is DIFFERENT from the retracted 50-pip
    tolerance peel; this is event-triggered containment at bar level.
  - If Gate X is MSS 10-min window × zone-containment-at-CHoCH, Gate 2 candidate =
    widen window to 30-min OR drop the zone-containment coupling (MSS proves direction,
    zone proves location — they do not need to coincide at the same price).
  - If Gate X is sweep (120-min for SB, Asian for Judas), Gate 3 candidate = check
    whether the sweep DEFINITION is at fault: `_swept_asian_extreme` requires
    `low < level AND close > level` in the same bar; a sweep followed by close back
    on the correct side a few bars later is also a valid liquidity grab.
  - Each candidate relaxation must be ICT-canonical, not a peel. Document the ICT
    citation (which chapter / which teaching) you relax to.

PHASE 2 — hypothesis-driven relaxation + measurement (1 day):
  - Pick the single highest-value relaxation from Phase 1 (ranked by expected signal
    yield × canonical fidelity).
  - Implement it in `src/v17/setups/` with regression tests.
  - Run the 4-year backtest both symbols. Record trade count.
  - If trade count < min_oos_trades (200), the relaxation is insufficient. Document
    the delta and iterate ONCE with the next-ranked relaxation. Stop at the second
    iteration if still insufficient — further iteration is strategy redesign, which
    moves to Phase 4.
  - If trade count ≥ 200, go to Phase 3.

PHASE 3 — M6 gate run (half day):
  - Walkforward 12 folds, 2021–2024, both symbols.
  - Monte Carlo (hybrid_mc, 1000 runs) on each.
  - Check every M6 threshold. ALL must pass. One failure = overall FAIL.
  - If pass: inflate `COST_MODEL` spread by 50% and 100%, repeat Phase 3.
  - Any gate that passes at 0% inflation and fails at 50% is not deployable. Document.
  - All three (0%, 50%, 100%) must pass M6 for the strategy to be "live-ready".

PHASE 4 — if Phases 2-3 fail to produce a passing config:
  - This is where the user's "don't tell me impossible" rule kicks in HARDEST.
  - Enumerate the specific reasons each attempted config failed, with per-gate
    drop numbers. Not opinions. Numbers.
  - For each reason, propose ONE concrete alternative: (a) different timeframe
    (e.g., 5m or 15m bars instead of 1m), (b) different setup from the allowed
    sources, (c) different symbols (DXY, Gold, indices).
  - Implement the single highest-expected-yield alternative as a new SetupEngine
    subclass. Re-run M6.
  - If this alternative passes M6: Outcome B.
  - If this alternative fails M6: that is Outcome D with the measured proof.
    "No single mechanical setup on this data clears M6" with per-gate drop tables
    IS a valid, non-fake answer. The user asked for no fake results — this is
    the honest result, backed by evidence.

Allowed primary sources for Phase 4 setup candidates (per workflow §13):
  - Peer-reviewed FX journals (Journal of Finance, Review of Financial Studies,
    Journal of Financial Economics, Journal of Banking & Finance).
  - BIS working papers; central bank research departments.
  - SSRN papers with ≥ 50 citations.
  - Published quant books by named authors (Carver, Chan, Pardo, Narang, Grinold,
    Pedersen).
  - FTMO's own published trader statistics (what historical passers actually did).

Forbidden sources: YouTube, Discord, retail trading courses, book reviews, X/Twitter
threads, LLM-generated strategy claims, "I asked ChatGPT and it said".

Deliverables:
  - `docs/research/<YYYY-MM-DD>-profitability-finding.md` — the written report.
  - For every claim: the exact run_id and metrics.json path backing it.
  - For every bug fix (if any): file:line, before/after test, regression suite result.
  - Final recommendation: A / B / C / D with the evidence.

Hard rules (non-negotiable):
  - Every number you report must have a committed run_id. No "my calculation shows".
  - Every "pass" must survive the 50% and 100% spread inflation.
  - Every "fail" must come with per-gate drop numbers.
  - If you are tempted to loosen min_pip_sl below 2, min_rr below 1.5, min_oos_trades
    below 200, or any M6 threshold — STOP. That is rigging the gate, not finding edge.
  - If you cannot find edge after Phases 0-4, the final sentence of your report is:
    "No profitable configuration found within v17's current interface and this data.
    Evidence attached. Outcome D." That is an acceptable answer. "Fake pass" is not.

Time budget: 3 working days maximum. If you have not reached A/B/C/D with evidence
by then, deliver a status report with the best current hypothesis and stop. Do not
burn further compute on an unresolved question — escalate to the user.

Begin with Phase 0. Do not skip.
```

---

## Why this prompt is shaped this way

- **Blocks fake results four ways:** committed-run requirement, spread stress, min_oos_trades floor, forbidden-sources list.
- **Blocks "impossible" without proof:** Outcome D requires per-gate drop tables for at least 3 alternative setups. Agent can't shortcut to "no edge" without doing the work.
- **Blocks gate rigging:** explicit list of thresholds that cannot be lowered to make a pass.
- **Blocks peeling-to-fake-pass:** canonical gates + lookahead-safe mitigation + trade-level guards must stay. The ONLY way to pass is to find real edge, not relax safety.
- **Finite time budget:** 3 working days. Prevents indefinite investigation.
- **Honest terminal state:** Outcome D is permitted. "Nothing passed. Here's the evidence." is the correct answer in the no-edge case.
