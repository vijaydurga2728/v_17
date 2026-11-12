# Cycle 6 — SPX-Led Intraday Risk-On/Off FX (PRE-REG DRAFT)

**Status:** DRAFT 2026-11-12, pending user sign-off. FROZEN upon first commit of implementation code.
**Branch:** `cycle6-spx-led-fx` (suggested, from `ensemble-h1-cycle4`).
**Prior cycles:** SB, ORB, Gap-Fade, ensemble-h1, FX cointegration — SHELVED. RSI2-NAS100 live in 30-day demo.
**Author:** vijaytectra. **Date:** 2026-11-12.

---

## 1. Thesis

Intraday moves in AUDUSD and USDJPY are strongly beta-driven by real-time US equity index direction (SPX). When SPX trends away from its session VWAP with positive slope, institutional risk-on flows push AUDUSD (risk-on currency) and USDJPY (funding-currency weakness) in the same direction. The edge is **not** the index-FX correlation itself, which is widely known and already priced. The edge is in **separating the regime decision from the entry decision**: SPX decides direction (slow, low-noise, index-driven), the FX pair's own M5 structure decides timing (fast, pair-specific). Prior cycles coupled regime and entry into one signal, which created either over-fitting (ORB, Gap-Fade) or spread-decay failure (cycle 5). This is the first cycle where the regime signal and the execution signal come from **different instruments**.

## 2. Universe (LOCKED)

- **Traded instruments:** AUDUSD, USDJPY (M1 bid/ask, resampled to M5).
- **Regime driver:** USA500IDXUSD (SPX, M1 bid/ask, resampled to M5).
- **Blackout source:** `forex_factory_cache` folder, filtered to `impact == "high"` on `{USD, AUD, JPY}`.
- All three series present in `C:\Users\Vijayakumar R\Documents\` — no new vendor needed.

## 3. Data split (LOCKED before any backtest)

- **Dev:** 2015-01-01 → 2023-12-31 (9 years).
- **Holdout:** 2024-01-01 → 2026-10-14 (2.79 years, bounded by SPX data end).
- **Demo:** 30 calendar days on live data, scheduled only after holdout passes. Earliest practical start 2026-12-12 (after cycle 4B demo window ends 2026-12-11); exact start date decided at S6 kickoff.
- No walk-forward inside dev — single-shot parameter tuning across all of dev. Multiplicity controlled by scheme-1 MCPT and paired-alpha ablation, not by WF folds.

## 4. Capital & FTMO alignment (LOCKED)

- FTMO Standard $10k.
- 0.5% risk per trade of current equity.
- Both pairs may be live simultaneously, capped at 0.75% combined open risk (portfolio cap).
- Soft daily loss stop: −1.5% realized (blocks new entries, existing run).
- Hard daily loss stop: −2.5% realized (flattens all at next M5 open, blocks rest of day).
- Daily profit stop: +2.0% realized (flattens all, blocks rest of day).
- Max 8 trades per UTC day.
- 3 consecutive losing trades on a UTC day → block new entries rest of day.

## 5. Signal stack (LOCKED)

All timestamps UTC. All indicators computed on bar close. Session anchor 08:00 UTC, resets daily.

### 5.1 Regime layer (SPX, M5)

- `SPX_VWAP[t]` = session VWAP of SPX mid = (bid + ask) / 2, anchored 08:00 UTC, reset daily.
- `SPX_ATR[t]` = ATR(14) of SPX M5.
- `SPX_SLOPE[t]` = OLS slope of `SPX_VWAP[t-11 .. t]` (12 bars = 60 min).
- Regime state at bar `t`:
  - `LONG_BIAS` if `SPX_close[t] > SPX_VWAP[t] + K × SPX_ATR[t]` AND `SPX_SLOPE[t] > 0`
  - `SHORT_BIAS` if `SPX_close[t] < SPX_VWAP[t] − K × SPX_ATR[t]` AND `SPX_SLOPE[t] < 0`
  - `FLAT` otherwise

### 5.2 Micro-trigger layer (per FX pair, M5)

- `FX_VWAP[t]` = session VWAP of FX mid, anchored 08:00 UTC.
- `FX_ATR[t]` = ATR(14) of FX M5.
- Pullback condition at `t`: within `[t-2, t-1, t]`, pair's low ≤ `FX_VWAP[bar]` ≤ pair's high for ≥ 1 bar.
- Confirm bar at `t`:
  - Long: `close[t] > FX_VWAP[t]` AND `close[t] > open[t]` AND `(close[t] − open[t]) ≥ C × FX_ATR[t]`
  - Short: mirror.
- Direction alignment: long only if regime = `LONG_BIAS`; short only if regime = `SHORT_BIAS`. `FLAT` blocks entries.

### 5.3 Tunable parameters (grid-searched on dev, locked before holdout)

| Param | Meaning | Grid | Count |
|-------|---------|------|-------|
| `K` | Regime ATR threshold | {0.2, 0.3, 0.4, 0.5} | 4 |
| `slope_window` | SPX VWAP slope bars | {8, 12, 16, 20} | 4 |
| `C` | Confirm body × ATR | {0.3, 0.4, 0.5} | 3 |

Total grid: **48 configurations.** Selection metric: dev net Sharpe. One parameter set across both pairs — no per-pair tuning. EMA(20) trail period is **not** tuned.

## 6. Execution mechanics (LOCKED)

### 6.1 Entry

- Market order at open of bar `t+1`, after confirm bar closes at `t`.
- Long fills at ask, short fills at bid (spread paid once on entry).
- Position split into two equal legs, Leg-A and Leg-B.

### 6.2 Initial stop

- Beyond swing low (long) or swing high (short) of `[t-2, t-1, t]`.
- Floored at entry ∓ `0.75 × FX_ATR[t]` — if swing stop is tighter than 0.75×ATR, widen to 0.75×ATR.
- `R = |entry − initial_stop|` (price).
- `R_pips = R / pip_size`.

### 6.3 Position sizing

- `r_budget = 0.005 × equity_sod`, where `equity_sod` = equity at **start of current UTC day** (fixed for the whole day, not mark-to-market). Prevents intraday size escalation on winning days and size collapse on losing days.
- **AUDUSD:** `pip_size = 0.0001`, `pip_value_per_1.0_lot = 10 USD`, `lots_total = r_budget / (R_pips × 10)`, round DOWN to 0.01.
- **USDJPY:** `pip_size = 0.01`, `pip_value_per_1.0_lot = 1000 / USDJPY_price` (USD), `lots_total = r_budget / (R_pips × pip_value)`, round DOWN to 0.01.
- `lots_leg_A = lots_leg_B = round_down(lots_total / 2, 0.01)`. If `lots_leg_A < 0.01`, skip trade.
- Portfolio cap: if new entry would push combined open risk above 0.75% of `equity_sod`, skip. "Open risk" per open leg = `|current_price − current_stop| × lots × pip_value`, using the live trailed stop (not initial stop). Breakeven-moved or trailed stops reduce open risk and free capacity.

### 6.4 Exits

- **Leg-A target:** entry + 1R (long) or entry − 1R (short), hard limit. On fill, move Leg-B stop to breakeven.
- **Leg-B trail (activates only after Leg-A fills):** on each M5 close `u`:
  - Long: `new_stop = max(current_stop, EMA20[u] − 0.25 × FX_ATR[u])`. Stop only ratchets up.
  - Short: mirror.
- **Hard time stop:** 19:30 UTC — close any open leg at the 19:30 M5 bar's close price.
- **No regime-flip exit.** Trailing + time stop handle reversal risk.
- **Initial-stop exit:** if both legs open and price hits initial stop, both exit together. If only Leg-B open, only Leg-B exits at trailed stop.

### 6.5 Spread + cost model

- Spread paid using actual bid/ask from M1 data at fill timestamp — no synthetic slippage on top.
- Commission: $3.50 per round-trip per standard lot (FTMO spec), scaled by actual lot size.
- Applied to every fill: entry, Leg-A target, Leg-B exit (trail, time stop, or initial stop).

### 6.6 No-pyramiding rule

- One open position per pair per direction per session.
- If stopped out, no re-entry same direction same session same pair. Opposite direction allowed if regime flips.

## 7. Session windows & blackouts (LOCKED)

### 7.1 Entry window

- Entries allowed only when signal bar's close timestamp is in `[08:05 UTC, 19:00 UTC]`.
- Additional warmup gate: SPX bars-since-session-start ≥ 12 (regime fully defined). Dominates 08:05 floor on normal days.
- **First 5 min of NY (13:30:00 – 13:34:59 UTC):** entries blocked. Signals logged, not acted on.

### 7.2 News blackout

- Load `forex_factory_cache`. Filter `impact == "high"` on `{USD, AUD, JPY}`.
- For each event at time `E`, blackout window `[E − 15 min, E + 15 min]`.
- Entry blocked inside any blackout window.
- Open positions are **not** force-closed on news — stops/trail/time-stop handle them.
- If calendar file is missing or `max(calendar_ts) < sim_date − 48h`, **skip whole day** (fail-closed).

### 7.3 Day boundaries

- "Trading day" = UTC date of entry bar.
- 19:30 UTC hard flat → no cross-midnight exposure ever.
- Daily counters (realized P&L, trade count, consecutive losses) reset at 00:00 UTC.
- Equity carries across days.

### 7.4 Circuit-breaker precedence

Evaluated at each FX M5 bar close during the trading day:

1. Hard loss stop (−2.5% realized) → flatten + block day.
2. Daily profit stop (+2.0% realized) → flatten + block day.
3. Soft loss stop (−1.5% realized) → block new entries, existing run.
4. 3 consecutive losses → block new entries.
5. 8 trades/day cap → block new entries.

## 8. Validation gates (ALL PRE-REGISTERED)

### 8.1 Dev gates (must pass before touching holdout)

- **D1.** Dev net Sharpe (after spread + commission, both pairs combined) ≥ 1.0.
- **D2.** Dev scheme-1 MCPT p-value ≤ 0.05 against random-label permutation null.
- **D3.** Dev profit factor ≥ 1.25.
- **D4.** Dev max observed daily loss ≤ 3.0%.
- **D5.** Dev max consecutive losing days ≤ 5.
- **D6.** Dev trade count ≥ 800.

### 8.2 Paired-alpha ablation gates (dev)

- **A1 (vs random-entry null):** strategy dev Sharpe beats Null-A with p ≤ 0.05. Null-A = random M5 entries with same per-pair-per-direction count distribution and same exit rules.
- **A2 (vs regime-only null):** strategy dev Sharpe beats Null-B with p ≤ 0.10. Null-B = enter every M5 bar where regime flips into `LONG_BIAS` or `SHORT_BIAS`, same exits.
- **A3 (vs micro-trigger-only null):** strategy dev Sharpe beats Null-C with p ≤ 0.10. Null-C = fire M5 VWAP pullback entries without SPX regime gate, same exits.
- If A1 passes but both A2 and A3 fail → regime filter and micro-trigger each add no alpha → **shelve.**

### 8.3 Holdout gates (must pass before 30-day demo)

- **H1.** Holdout net Sharpe ≥ 0.7 × dev Sharpe.
- **H2.** Holdout MCPT p-value ≤ 0.10.
- **H3.** Holdout profit factor ≥ 1.15.
- **H4.** Holdout max daily loss ≤ 3.0%.
- **H5.** No single calendar month in holdout with net return < −5%.

### 8.4 Pre-registered shelve policy

- Any failed dev gate (D1–D6, A1–A3) → shelve.
- Any failed holdout gate (H1–H5) → shelve.

### 8.5 Rescue policy (one-shot, theory-grounded only)

- Allowed only if: holdout Sharpe decay ≥ 50% AND an identifiable SPX volatility regime shift (specific dated break) explains the decay.
- Rescue = extend dev window once to include the regime break's start date. **Grid stays the same, boundary moves once.**
- No grid re-tune. No filter addition. No second rescue.
- Rescue failure → shelve.

## 9. Implementation phases

Each phase ships one artifact and one gate.

| Phase | Deliverable | Gate |
|-------|-------------|------|
| **S1** | M1 CSV loaders (bid/ask join, mid compute), M5 resampler (left-closed, label=right, drop bars < 5 M1 ticks), parquet cache `data/bars_m5/<SYM>/{dev,holdout}/year=YYYY/`, `forex_factory_cache` → parquet index `(ts_utc, currency, impact)`. | Row counts, no-NaN mids, timezone correctness, calendar coverage on NFP 2020-03-06, FOMC 2022-06-15, BOJ 2022-12-20. |
| **S2** | Signal engine: regime state, micro-trigger, per-bar signal log (no execution). | Signal counts sane (~1500–4000 raw signals per pair over 9 years), regime distribution not degenerate. |
| **S3** | Backtest engine: two-leg manager, stop/trail/time-stop, bid/ask fills, blackouts, circuit breakers. | Deterministic replay (same inputs → byte-identical trade log), sizing math verified on 20 hand-computed trades. |
| **S4** | Dev run of all 48 configs, scheme-1 MCPT, three paired-alpha ablations. | D1–D6 + A1–A3. |
| **S5** | Holdout run with locked parameters. | H1–H5. |
| **S6** | Promote to 30-day paper demo on live data 2026-11-13+. | Handled by existing demo infra; outside this spec. |

## 10. Artifacts per phase

- Parquet caches (S1).
- Signal log CSV (S2).
- Trade log CSV + equity curve JSONL (S3, S4, S5).
- MCPT JSON + paired-alpha JSON (S4, S5).
- Pre-reg gate report markdown under `docs/superpowers/plans/c6_*_report_YYYY-MM-DD.md` (S4, S5).

## 11. Known failure modes & mitigations

| Risk | Mitigation |
|------|-----------|
| SPX M5 bar misaligned with FX M5 bar | Shared 5-min grid, both resampled with identical left-closed label=right, bars with < 5 M1 ticks dropped, hard assertion on timestamp equality in S1 gate. |
| Session VWAP contaminated by illiquid 08:00–08:05 noise | 12-bar SPX warmup gate ensures regime first available at 09:00 UTC; FX warmup same. |
| SPX-FX lead-lag unstable across 2015–2026 | Regime is bar-coincident, not lag-based. The "lead" is inside the 5-min bar. Removes lead-window estimation risk. |
| 2020 COVID + 2022 BOJ breaks correlation structure | Dev set spans both regimes; if dev passes but holdout fails on identified regime shift, rescue policy (§8.5) applies. |
| Overlapping Leg-A and Leg-B create accounting ambiguity | Logged as two separate logical positions with the same entry; combined P&L reported per trade. |
| EMA(20) trail whipsaw on low-vol afternoons | 0.25× ATR buffer below EMA prevents micro-touches; the ratchet-only rule prevents stop loosening. |
| FTMO 5% daily / 10% total breach | Soft/hard caps at 1.5%/2.5% give 2×–2.5× safety; backtest reports max daily loss distribution; no rescue allowed if backtest shows any day > 3%. |
| News calendar missing or stale | Fail-closed — whole day skipped if calendar stale > 48h. |

## 12. Explicit non-goals

- No per-pair parameter tuning (one set for both AUDUSD and USDJPY).
- No walk-forward inside dev.
- No regime-flip exits.
- No second rescue.
- No profit-based filter after backtest (no post-hoc pair/parameter dropping).
- No live demo until all dev and holdout gates pass.

## 13. Sign-off

- [ ] User approves Sections 1–12.
- [ ] Spec committed to `cycle6-spx-led-fx` branch.
- [ ] Spec frozen — further changes require a new ADR.
