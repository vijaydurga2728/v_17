# Prompt: Build a profitable v17 trading system

**Composed from:** `MASTER_ANTIGRAVITY_WORKFLOW.md` §0 (Task Router) + §13 (Research) + §12 (Performance / measurement discipline) + §3 (Systematic debug, when claims need evidence).

**Intended consumer:** an engineering/research agent (fresh context, no v17 history).

**Why this is a composite, not a single template:** "build a profitable system" is not an engineering task. The system is already built (M1–M10 shipped, 305 tests pass). Profitability is a *strategy* claim about the chosen setups (ICT Silver Bullet + Judas Swing on EURUSD / GBPUSD). The honest work is: measure the real edge, decide whether to keep, replace, or extend the strategy — then only after that, engineer. Treating this as a code task will produce more code and no edge.

---

```text
Task: Determine whether the current v17 strategy stack has measurable edge, and if not, 
recommend the smallest change that could — before any further engineering.

Expected result: an evidence-grounded recommendation of ONE of these outcomes, with the data 
that justifies it:
  A. Keep current setups (Silver Bullet + Judas Swing) — real edge detected on walkforward.
  B. Modify current setups (specific parameter tuning, specific gate changes) — edge is 
     latent but blocked by over-tight filters; measurable improvement from a surgical change.
  C. Replace current setups (named candidate strategy with published edge evidence) — 
     current ICT setups show no edge across all tested regimes and the engineering effort 
     is better spent on a strategy with documented microstructure or statistical support.
  D. Shelve the live-trading goal entirely — no setup within the current M1–M10 architecture 
     clears the M6 validation gate across walkforward; the honest result is "do not deploy".

Constraints / non-goals:
  - Do NOT write new strategy code, add new setups, or refactor engines without first 
    establishing the edge question's answer.
  - Do NOT loosen the M6 validation gate (PF >= 1.3, p5_pf > 1.0, p95_max_dd_pct < 15%, 
    walkforward passed-fold ratio >= 0.6) to make a result pass.
  - Do NOT accept backtest results that are produced by a system with trades = 0. A zero-
    trade backtest is a diagnostic result, not a profitability result.
  - Do NOT substitute enthusiasm for evidence. Retail popularity of a strategy is not 
    evidence of edge. ICT content volume on YouTube is not evidence of edge.
  - Preserve the current M1–M10 architecture. Any strategy change rides on existing 
    `SetupEngine` / `RiskEngine` / `StructureEngine` interfaces.

Inspect the following before proposing anything:
  1. `docs/SPEC.md` — the committed goal and non-goals of v17.
  2. `docs/superpowers/plans/00-INDEX.md` — module history.
  3. `src/v17/setups/silver_bullet.py` and `src/v17/setups/judas_swing.py` — current entry logic.
  4. `src/v17/structure/` — bias, swings, FVG, OB, MSS, sweeps as implemented.
  5. `src/v17/backtest/` — EventLoop, precompute, montecarlo, walkforward.
  6. `scripts/diag_setup_gates.py` — the setup-firing diagnostic.
  7. `.superpowers/sdd/2026-10-29-m11-setup-firing-fix/progress.md` — the current M11 state 
     (both fixes shipped, trades still = 0 on June 2024 EURUSD).
  8. `runs/` — any existing run artifacts (metrics.json, trades.parquet, montecarlo.json).

Classify this task as one or more of (per workflow §0):
  - Research / dependency choice
  - Performance investigation (measurement discipline for profitability claims)
  - Possibly bug fix (if setup-firing is still broken, the "no edge" conclusion is premature)

Phase 1 — reality check (read-only, 1-2 h):
  - Run `scripts/diag_setup_gates.py` across the already-sampled months (EURUSD Q1/Q2/Q3 2024, 
    GBPUSD Q1/Q3 2024). For each: how many SB-window bars, how many pass bias, zone, sweep, 
    MSS, RR, pip-SL gates. If `signals > 0` anywhere, run full backtest + metrics on that 
    window. If `signals == 0` everywhere, the problem is the setup, not the data.
  - Report which gate drops the most candidates and in what proportion. Numbers only.

Phase 2 — edge evidence (walkforward, 1 day):
  - If any configuration fires signals: run `v17 walkforward --folds 12` on at least two years 
    of EURUSD and two years of GBPUSD. Record: passed_folds / total_folds, OOS PF per fold, 
    OOS max_dd_pct per fold. The M6 passed-fold ratio >= 0.6 bar is the honest gate.
  - Run `v17 montecarlo --run <id> --runs 1000` on each fold meeting the PF threshold. Report 
    p5_pf and p95_max_dd_pct — those are the true gate values, not point estimates.
  - Deliberately include a cost-sensitivity check: inflate `spread_pips` by 50% and 100% 
    and re-measure. Backtest-at-mid vs live-at-ask erosion is 30-60% in FX minute-bar trading.

Phase 3 — primary-source research for alternatives (half day):
  - If Phase 2 shows no edge or marginal edge: survey published FX edges with ACTUAL evidence.
    Allowed sources: peer-reviewed journals (Journal of Finance, Review of Financial Studies, 
    Journal of Financial Economics), BIS working papers, central bank research, SSRN with 
    citation count > 20, published quant books with named authors (Carver, Chan, Narang, 
    Pardo). Not allowed as a source: YouTube, retail trading courses, Discord screenshots, 
    "ICT taught me" content, reviews of books rather than the books themselves.
  - Candidate families to assess: carry (Lustig-Verdelhan), trend following on daily/weekly 
    (CTA literature, Hurst-Ooi-Pedersen), FX momentum (Menkhoff et al.), order-flow / 
    microstructure (Evans-Lyons). For each: edge magnitude in Sharpe, drawdown profile, 
    data requirements, implementability inside v17's existing interfaces.
  - Honest comparison: current ICT setups have NO peer-reviewed edge evidence to date. Any 
    candidate is competing against zero, not against a baseline.

Phase 4 — recommend ONE outcome from A–D above:
  - Lead with the evidence, then the recommendation, then the smallest implementation path.
  - If the recommendation is C (replace setups): propose the smallest vertical slice as an 
    M12 plan — a single new `SetupEngine` subclass implementing the chosen strategy, no 
    other code touched, re-use existing risk engine, backtest harness, validation gate.
  - If the recommendation is D (shelve): propose repurposing v17's infrastructure for paper-
    trading / scanning / education, not live deployment. Honest end-states are OK.

Deliverables:
  - A written assessment at `docs/research/2026-10-29-edge-assessment.md`.
  - Phase 1 diagnostic table.
  - Phase 2 walkforward + MC tables (if applicable).
  - Phase 3 candidate strategy comparison (if applicable).
  - One recommendation with named next step.

Prohibitions:
  - Do not claim a Sharpe without stating sample size, period, cost assumptions, and OOS vs 
    IS split.
  - Do not call a strategy "profitable" from a single backtest fold.
  - Do not invent benchmarks, citations, broker fees, or spreads.
  - Do not deploy, place real orders, or move the GATE_PASSED sentinel.
  - Do not install new runtime deps without a research-sourced reason.
  - If every Phase 2 result fails M6, say so plainly. "No edge detected" is the honest result
    and does not require further rework before being reported.

A session that returns Outcome D with evidence is more valuable than a session that returns 
Outcome A with hand-waving. Measure, report, decide.
```

---

## Why this prompt is shaped this way

- **Front-loads a reality check.** The system currently returns zero trades. Running walkforward on a zero-trade system is a waste. Phase 1 forces a signal-firing check before any edge claim.
- **Puts the validation gate on the critical path.** M6 is already specced (`PF >= 1.3`, `p5_pf > 1.0`, `p95_max_dd_pct < 15%`, passed-fold ratio `>= 0.6`). The prompt reuses it rather than inventing a new bar.
- **Includes cost sensitivity.** Minute-bar FX backtests at mid-price routinely overstate edge by 30–60%. A profitability claim without a spread-inflation check is not a profitability claim.
- **Reserves one outcome for "shelve the goal".** Most retail algo projects should end here. Making it a legitimate outcome prevents the agent from forcing a positive answer.
- **Allowed-sources list.** Prevents the agent from citing retail content as research. "Published edge" means the kind of edge that has survived someone else's hostile peer review.
- **Blocks "add more code before measuring".** All four current M11 problems are strategy problems, not engineering problems. The prompt makes writing more code a Phase-4 action, gated on evidence from Phases 1–3.
