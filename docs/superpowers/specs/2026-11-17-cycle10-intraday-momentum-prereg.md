# Cycle 10 — Market intraday momentum on NAS100 (pre-registration DRAFT)

**Status:** FROZEN 2026-11-17 (user "yes to all" on Q-A, Q-B, Q-C). Committed before any cycle 10 code was
written or any cycle 10 result computed.
**Date drafted:** 2026-11-17
**Branch:** `cycle10-intraday-momentum` (from `b5371a0`, cycle 9 Phase 4 entrypoint)
**Authorizing message:** user "yes to all", 2026-11-17 (candidate = intraday momentum; 3 slots, one per published
rule; reuse cycle 9 machinery; Bonferroni denominator 135; gates fixed before any run).

Any deviation after freeze requires a written ADR with explicit user re-authorization (same rule as cycle 9).

---

## 1. Hypothesis

The NAS100 return over the last 30 minutes of the NYSE cash session continues the direction of the earlier
part of the day (market intraday momentum). Three published rules are tested as written, with no tuning:

| Slot | Source | Signal | Trade |
|---|---|---|---|
| `G` | Gao, Han, Li, Zhou (2018), *JFE* 129(2) 394-414 | Return from previous close to 10:00 ET | 15:30 → 16:00 in signal direction |
| `B` | Baltussen, Da, Lammers, Martens (2021), *JFE* 142(1) 377-403 | Return from previous close to 15:30 ET ("rest of day", verified in the authors' PDF) | 15:30 → 16:00 in signal direction |
| `Z` | Zarattini, Aziz, Barbon (2024), SSRN 4824172, as independently replicated in `Ascensao/Intraday-momentum-strategy` | Close outside the 14-day "noise area" **and** beyond VWAP, checked every 30 min | Intraday, flat by 16:00 |

Published mechanism (Baltussen et al.): gamma hedging by options market makers and leveraged ETFs.

Not tested here: trend filters, leverage/vol targeting, other indices, other sessions. Those are separate hypotheses.

## 2. Instrument and data

- Symbol `USATECHIDXUSD` (NAS100 CFD), paired bid/ask M1 from
  `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/{dev,holdout}/year=YYYY/month=MM/data.parquet`
  (same source as cycle 9; dev data audited clean on 2026-11-17).
- **Timestamp convention:** `ts_utc` is the bar **start**. Verified 2026-11-17 (09:30 bar = opening minute; data
  closes match official NDX closes within 0.5 pt on 2020-02-19 and 2021-11-19).
- `mid_x = (bid_x + ask_x) / 2`. Signals use mid prices. Fills use bid/ask.
- "Price at time T" means the **close of the M1 bar that starts at T − 1 min** (e.g. price at 10:00 = close of the
  09:59 bar; price at 16:00 = close of the 15:59 bar).
- Volume (slot Z VWAP only) = `bid_volume + ask_volume`. This is broker **tick volume**, a proxy for exchange
  volume. Its level shifts in 2018; VWAP uses only within-day relative weights, so the shift does not matter, but
  the proxy is a stated limitation (§12).

## 3. Windows

- **Dev:** 2015-01-01 → 2022-12-31 (same as cycle 9).
- **Holdout (sealed):** 2023-01-01 → 2026-11-16. Touched at most once per slot, after dev Tier 1-3 pass and a
  separate user authorization.
- Loading reuses `v17.backtest.c9_runner.load_m1` (dev reads 2015-2022 partitions only; holdout requires
  `allow_holdout=True`; duplicate audit; files-read audit).

## 4. Calendar

- XNYS via `pandas_market_calendars==5.6.1` (ADR-001-G pin). **Full 09:30-16:00 days only**; half-days excluded
  from trading and never used as "previous close".
- "Previous close" for day D = price at 16:00 of the most recent full day before D. If that day has no data, D is
  not traded (same rule as cycle 9 IMPL-1).
- Unlike cycle 9, the `[15:45, 16:00)` interval **is used**: the trade window is 15:30-16:00 by definition.

## 5. Common definitions

- `PC(D)` = mid price at 16:00 of the previous full day.
- `O(D)` = mid open of the 09:30 bar of D.
- **R unit (risk normalization, all slots):** `RU(D) = entry_price × mean_{k=1..14} |C(D−k) / O(D−k) − 1|`, where
  `C` is the 16:00 mid price, over the 14 previous full days with data. It is the typical open-to-close move,
  known before D opens. Days without 14 prior full days are not traded (warm-up).
  `R = pnl_points / RU(D)`. Intended sizing: 1R = 0.5% of equity, so 8R = 4% (inside FTMO's 10% max loss).
- **Required bars:** if any M1 bar needed for a signal, entry or exit is missing, that slot does not trade that
  day. Counts are reported in the data audit.
- **Fills:** long entry `ask_o`, long exit `bid_*`; short entry `bid_o`, short exit `ask_*`. Slippage 0 pt
  baseline; +1 pt adverse on every fill as a sensitivity report (§10).
- One trade at a time per slot. No stop-losses or targets unless the source rule has them (none for G and B).

## 6. Slot G — Gao et al.

1. `s = price(10:00) / PC(D) − 1`. `s > 0` long; `s < 0` short; `s == 0` no trade.
2. Entry at the **open of the 15:30 bar**. Exit at the **close of the 15:59 bar** (= 16:00).

## 7. Slot B — Baltussen et al.

1. `s = price(15:30) / PC(D) − 1` (close of the 15:29 bar). Sign rule as slot G.
2. Entry at the **open of the 15:30 bar**. Exit at the close of the 15:59 bar.
   (The 15:29 bar closes at 15:30:00 and the 15:30 bar opens then; no look-ahead.)

## 8. Slot Z — Zarattini et al. noise-area momentum (as replicated)

Per minute `m` of day D (`m` = 1 for the 09:30 bar, ..., 390 for the 15:59 bar):

1. `move(D, m) = |mid_c(D, m) / O(D) − 1|`.
2. `σ(D, m)` = mean of `move(D−k, m)` over the previous 14 full days `k = 1..14`, requiring at least 13 values
   (replication: rolling 14, `min_periods=13`, shifted one day). Undefined → no signal at that minute.
3. Bands: `UB = max(O(D), PC(D)) × (1 + σ)`, `LB = min(O(D), PC(D)) × (1 − σ)`. Band multiplier 1. No dividend
   adjustment (CFD index price).
4. `VWAP(D, m) = Σ_{j≤m} v_j·tp_j / Σ_{j≤m} v_j` with `tp = (mid_h + mid_l + mid_c)/3`. Undefined while
   `Σ v = 0` → no signal.
5. **Check minutes:** `m ∈ {30, 60, ..., 360}` (closes of the 09:59, 10:29, ..., 14:59, 15:29 bars).
   Signal at a check: `+1` if `mid_c > UB` and `mid_c > VWAP`; `−1` if `mid_c < LB` and `mid_c < VWAP`; else `0`.
6. Position rule at each check (acting at the **open of the next bar**):
   flat & signal ±1 → open in that direction; holding & signal equals position → hold;
   holding & signal 0 → close; holding & signal opposite → close and open the opposite position at the same
   open (two trades).
7. Any open position is closed at the **close of the 15:59 bar**.
8. Each open-to-close is one trade; several per day are possible.
9. Deviation from the replication code: it fills at the close of the bar after the check (one minute later) and
   reverses one bar later. This spec fills at the next bar's open, the first executable price. Not expected to
   be material; stated for completeness.
10. The paper's vol-targeted sizing and leverage are not used. Results are in R (§5).

## 9. Grid

Exactly 3 slots, fixed order: `slot_index` 0 = `G`, 1 = `B`, 2 = `Z`. No parameters are varied.

## 10. Validation gates

**Tier 1 (dev, per slot)** — same thresholds as cycle 9:
- PF ≥ 1.3; trades ≥ 100; max drawdown ≤ 8R (on the per-trade cumulative R curve); Sharpe ≥ 0 (IMPL-11
  definition: sign of mean R).

**Tier 2 (dev MCPT)** — run for every Tier 1 passer. Exactly **100,000 permutations**,
`p = (exceed + 1) / (100,000 + 1)` where exceed = count(null mean R ≥ observed mean R).
- **Null (differs from cycle 9 — see §13 Q-B):** *direction permutation*. Keep every trade's entry and exit
  timestamps and fills machinery; randomly permute the observed vector of trade directions (preserves the exact
  number of longs and shorts, so index drift is not mistaken for skill); recompute each trade's net R with real
  bid/ask at the same timestamps. This tests whether the signal's **direction** carries information beyond
  timing and drift.
- Seeds: per-slot seed `20261117 * 1_000 + slot_index`; permutation `j` uses
  `numpy.random.default_rng([seed, j])`. Per-permutation log as cycle 9.

**Tier 3:** Tier 2 p ≤ **0.05 / 135 = 0.000370370** (cycles 6-10 slot count: 48 + 36 + 36 + 12 + 3). Do not relax.

**Tier 4 (holdout, separate authorization):** PF ≥ 1.2 and holdout MCPT p ≤ 0.05 (same null, holdout seed
`20261117 * 1_000 + 500 + slot_index`), at baseline **and** at +1 pt slippage.

**Slippage report:** Tier 1 metrics at +1 pt for every slot, reported side by side (reporting only on dev).

**Acceptance:** Tier 1 AND Tier 2 AND Tier 3 AND Tier 4 (baseline and +1 pt). Any failure → SHELVED. No rescue,
no parameter changes.

## 11. Verification required before any result is reported

1. Unit tests for: signal timing and no look-ahead, price-at-T convention, fills, sign rule, missing-bar skip,
   R unit warm-up, σ and VWAP construction, Z position state machine, MCPT null preserving long/short counts.
2. **Independent reimplementation** of all 3 slots (separate code path, as done for cycle 9) must match the main
   implementation trade by trade on dev before Tier 1 results are reported.
3. Holdout-read guard test (reuse cycle 9 pattern).
4. Data audit: duplicates, files read, missing bars per slot, sessions without R unit.

## 12. Known limitations and risks (accepted)

1. **Instrument:** published evidence is on SPY / index futures (NQ is in Baltussen's sample); this is a NAS100 CFD.
2. **Tick-volume VWAP** (slot Z) is a proxy for exchange volume.
3. **Weak signal:** Gao report predictive R² ≈ 1.6%. Even a real effect may produce PF well below 1.3 at one
   trade per day; Tier 1 may reject a real but thin edge (§13 Q-A).
4. **Costs:** a 2026 preprint frames intraday momentum on Micro Nasdaq futures as a falsification study after
   costs. Spreads are in the test; slippage sensitivity is reported.
5. **Post-publication decay:** McLean & Pontiff (2016) find anomaly returns ~58% lower after publication. Dev
   2015-2022 is entirely after Gao's working paper (2014-2015) and partly after Baltussen (2019-2021).
6. **Researcher knowledge:** NAS100 2015-2026 has been studied in cycles 4B and 9 (different hypotheses).
7. **FTMO practicality:** even a passing slot likely earns a small mean R per trade; reaching an FTMO profit
   target needs many trades. This affects deployment, not the statistical test.

## 13. Decisions resolved at freeze (user, 2026-11-17)

- **Q-A — Tier 1 PF threshold:** keep **PF ≥ 1.3**, same as every prior cycle.
- **Q-B — MCPT null:** **direction permutation** (§10). The cycle 9 session-shuffle null is not used, because it
  keeps each day's internal path and would reproduce intraday momentum inside the null.
- **Q-C — Slot Z volume:** keep slot Z with the **tick-volume VWAP proxy**. Bonferroni denominator stays 135.

## 14. Deliverables

- `src/v17/setups/c10_intraday_momentum.py`, `src/v17/backtest/c10_dev_pipeline.py`,
  `src/v17/validation/c10_mcpt.py`, `scripts/run_c10_dev.py`, `tests/unit/c10/`, `tests/integration/c10/`.
- Outputs in `out/c10/`: `data_audit.json`, `grid_report.csv`, `slippage_sensitivity.csv`, `trades/*.parquet`,
  `mcpt_report.csv`, `mcpt_perms_<slot>.parquet`, `run_manifest.json`, `phase4_dev_run.log`, `env_pin.txt`.

## 15. Sources

- Gao, Han, Li, Zhou (2018), Market intraday momentum, *JFE* 129(2): https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414
- Baltussen, Da, Lammers, Martens (2021), Hedging demand and market intraday momentum, *JFE* 142(1): https://www3.nd.edu/~zda/intramom.pdf
- Zarattini, Aziz, Barbon (2024), Beat the Market, SSRN 4824172: https://www.sfi.ch/de/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy
- Independent replication (code read 2026-11-17): https://github.com/Ascensao/Intraday-momentum-strategy
- McLean & Pontiff (2016), post-publication decay: https://Www.Gwern.net/doc/economics/2016-mclean.pdf
- MNQ intraday momentum falsification preprint: https://arxiv.org/pdf/2605.04004
