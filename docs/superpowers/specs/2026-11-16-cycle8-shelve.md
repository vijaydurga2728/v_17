# Cycle 8 Donchian Trend — SHELVE verdict

**Date:** 2026-11-16
**Branch:** `cycle8-donchian-trend` off `cycle7-gap-continuation-spx` HEAD `057e6a4`.
**Candidate role in ensemble plan:** #4.
**Pre-reg:** `docs/superpowers/specs/2026-11-16-cycle8-donchian-prereg.md`.

## Result summary

Grid: 18 configs × 2 symbols = 36 slots (`lookback_entry` × `lookback_exit` × `direction`).
Dev windows: LIGHTCMDUSD 2015-01-01 → 2023-12-31 (2806 D1 UTC-days). DOLLARIDXUSD 2018-01-01 → 2023-12-31 (1557 D1 UTC-days).

### Tier 1 (strict: PF ≥ 1.3, trades ≥ 30, max_dd ≤ 8R, sharpe ≥ 0)

- LIGHTCMDUSD: 0/18 pass.
- DOLLARIDXUSD: 0/18 pass.

### Tier 1' (user-authorized loosening: PF ≥ 1.3, trades ≥ 20, max_dd ≤ 12R, sharpe ≥ 0)

- LIGHTCMDUSD: 6/18 pass (5 long_only, 1 "both"). PF range 1.87-3.26, sharpe 3.3-6.0.
- DOLLARIDXUSD: 0/18 still fail. **DXY SHELVED outright.**

**Pre-reg deviation**: user explicitly authorized Tier 1 loosening after seeing the WTI long_only pattern miss `trades ≥ 30` by 7 and `max_dd ≤ 8R` by 1.17-3.5R. Logged as a researcher-degree-of-freedom.

### Tier 2 scheme-1 MCPT (block-bootstrap, block=10, 500 perms, seed=20261116) on 6 WTI Tier 1' survivors

| lookback_entry | lookback_exit | direction | n_trades | obs_mean_r | null_mean | null_q95 | p-value | Bonferroni α=0.0014 |
|---|---|---|---|---|---|---|---|---|
| 55 | 10 | long_only | 23 | +1.304 | +0.093 | +2.382 | 0.166 | fail |
| 40 | 10 | long_only | 29 | +1.035 | +0.116 | +2.145 | 0.210 | fail |
| 40 | 20 | long_only | 22 | +1.308 | +0.458 | +4.281 | 0.289 | fail |
| 55 | 20 | long_only | 20 | +1.155 | +0.419 | +3.918 | 0.303 | fail |
| 20 | 10 | long_only | 37 | +0.778 | +0.090 | +1.800 | 0.238 | fail |
| 55 | 10 | both | 46 | +0.859 | −0.061 | +1.584 | 0.154 | fail |

**0/6 pass raw α=0.05.** Best p = 0.154, two orders of magnitude above Bonferroni α=0.0014.

Artifact: `out/c8/mcpt_wti.csv`, `out/c8/mcpt_wti.log`.

## Interpretation

Block-bootstrap null preserves daily autocorrelation. Donchian run on bootstrapped WTI returns produces mean_r similar to Donchian run on real WTI returns. Translation: the observed edge is "WTI trends and Donchian catches trends," not "Donchian + WTI is a signal." The null hypothesis of random trend-persistence cannot be rejected.

Cycle comparison:
- Cycle 6 (SPX-led FX): PF < 1 throughout. No signal.
- Cycle 7 (Gap-continuation SPX): PF ~1.3, gate miss by 0.002. Signal small, gate strict.
- **Cycle 8 (Donchian WTI/DXY): PF up to 3.3, but MCPT says bootstrap matches. Pattern is regime, not strategy.**

## Decision

**SHELVED.** Both symbols. No Tier 3-5 run.

## Infra retained

- `scripts/run_c8_donchian_grid.py` — Donchian grid runner on M1→UTC-D1 resample. Generalizable.
- `scripts/run_c8_mcpt_wti.py` — block-bootstrap scheme-1 MCPT template. Reusable for any D1 strategy MCPT.
- `data/bars_m1_paired/{LIGHTCMDUSD,DOLLARIDXUSD}/year=2015..2026/` — cached M1 paired (gitignored).

## Next

Ensemble candidate **#5: carry-filtered FX trend on AUDJPY / NZDJPY D1.** Different asset class (carry-trade pairs). Different edge driver (rate differential + risk-on). Needs new data ingest (AUDJPY, NZDJPY M1 CSVs from Dukascopy).
