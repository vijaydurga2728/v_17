# Cycle 13 — Connors RSI(2) as published (200-day trend filter) on NAS100, SPX, US30 (pre-registration)

**Status:** FROZEN 2026-11-17. User answered "yes to all" to Q1-Q7 (one honest test, published rule, 3 indices,
broker-matched bars, judge each market on its own, hand-check table, pause demo). Committed before any cycle 13
result.
**Branch:** `cycle13-connors-published` (from `b7a17d3`).

## 1. Hypothesis and rule

Connors & Alvarez's published RSI(2) rule ("Short Term Trading Strategies That Work") has an edge on stock indices.
It differs from cycle 4B in **one** way only: the 200-day trend filter.

- Signal on D1 close: **close > SMA(200)** AND RSI(2) < 10 → buy at next bar open.
- Exit: first close > SMA(5) (from the entry bar on), else close of entry bar + 10 (TIME_CAP 10). Unchanged.
- Long only. One position at a time. Indicators on mid close. RSI(2) Wilder, SMA(5), SMA(200) simple.
- No 200-day exit rule (sources disagree; Q2 kept everything except the entry filter unchanged).
- Fills: long entry `ask_o`, exit `bid_c` (real spread, as cycle 12). R unit = 1% of signal mid close.

Implementation: `v17.setups.c12_rsi2_fx` engine with an added `trend_filter` option (default off, so cycle 12
behaviour is unchanged and its parity test still applies).

## 2. Markets and bars

- NAS100 `USATECHIDXUSD` (M1 from `.worktrees/sb-6-engine-gate/data`), SPX `USA500IDXUSD` and US30 `USA30IDXUSD`
  (M1 from `data/bars_m1_paired/`).
- D1 bars on the **17:00 New York rollover**, Mon-Fri (`build_fxny_d1`), shown on 2026-11-17 to match IC Markets
  MT5 USTEC D1 (719/720 dates). Cached at `data/bars_d1_ny17/<SYMBOL>/d1.parquet`.

## 3. Windows

- Dev: signal bars 2018-01-01 → 2024-12-31 (2015-2017 for indicator warm-up; SMA(200) needs ~200 bars).
- Holdout: 2025-01-01 → end of data, only for a market that passes dev.

## 4. Gates (each market judged on its own)

Dev: G1 PF ≥ 1.3, G2 trades ≥ 25, G4 R² ≥ 0.80, G5 cost-stress PF ≥ 1.1 (one extra entry spread per trade),
via `evaluate_secondary`; G3 reported only.
**Luck test (gating):** random-entry null as cycle 4B/12 — random long entries drawn from all eligible dev signal
bars, same exit rule and fills; statistic mean R; 10,000 permutations; p = (count ≥ observed + 1)/(10,001);
**α = 0.05/3 = 0.016667**. Seed `20261117 * 1_000 + 300 + market_index` (NAS=0, SPX=1, US30=2).
**Reported, not gating:** a stricter null drawing random entries only from bars where close > SMA(200), to show how
much comes from RSI(2) beyond the trend filter.

Holdout (dev passers): PF ≥ 1.3, WR ≥ 50%, max DD < 10R, luck p ≤ 0.016667 (seed +500).
Acceptance: dev and holdout pass for that market. Otherwise SHELVED. No further variants.

## 5. Hand-check (Q6)

For each market, a table of 5 dev trades (first 5): signal date, close, SMA(200), RSI(2), entry date and ask open,
exit date and bid close, exit reason, R. Written to `out/c13/hand_check.md`.

## 6. Known limits

- NAS100 2018-2026 and its 2025-26 holdout have been studied repeatedly (cycles 4B, 9, 10, 11, revalidation).
- The trend filter is a published rule, chosen before this run, but the decision to test it came after seeing
  that the unfiltered version fails on broker-matched bars.
