# Cycle 7 Gap-Continuation SPX D1 — SHELVE verdict

**Date:** 2026-11-16
**Branch:** `cycle7-gap-continuation-spx` off `cycle6-spx-led-fx` HEAD `d07a2a0`.
**Candidate role in ensemble plan:** #3.
**Pre-reg:** `docs/superpowers/specs/2026-11-16-cycle7-gap-continuation-prereg.md`.

## Result

36-config dev grid (gap_min × stop_R × direction) ran in <1s on 2322 RTH days (2015-01-01 → 2023-12-31). Artifact: `out/c7/dev_grid.csv`.

**Tier 1 gate:** PF ≥ 1.3, trades ≥ 150, max_dd ≤ 6R, sharpe ≥ 0.

**Pass count: 0 / 36.** Closest two:

| gap_min | stop_R | direction | trades | PF | mean_r | sharpe | max_dd | miss |
|---|---|---|---|---|---|---|---|---|
| 0.004 | 0.5 | long_only | 464 | 1.292 | +0.107 | +1.76 | 11.01R | PF −0.008, dd +5R |
| 0.006 | 1.5 | long_only | 264 | 1.298 | +0.040 | +1.59 | 4.32R | PF −0.002 |

## Pattern observation (not grounds for rescue)

All 12 `long_only` configs are PF > 1.0; all 12 `short_only` configs are PF < 1.05 (11 < 1.0). Gap-up continuation shows a monotone positive edge over the grid axis. Short-side gap-continuation is dead on SPX dev 2015-2023.

Not enough to override the pre-reg gate. PF miss of 0.002 on the leading config is below measurement noise, but loosening Tier 1 by that amount is a precedent that eliminates the gate.

## Decision

**SHELVED** per pre-reg §13: "If zero configs pass Tier 1, strategy is SHELVED same day. No param search beyond this grid."

No Tier 2 MCPT run. No holdout touched.

## Infra retained

- `scripts/build_d1_rth_spx.py` — RTH-aligned SPX D1 builder. Reusable for any SPX RTH-D1 strategy.
- `scripts/run_c7_grid.py` — gap-continuation grid runner. Reusable template for D1 single-factor grids.
- `data/bars_d1_rth/USA500IDXUSD/year=2015..2026/` — RTH D1 bars cached.
- `data/bars_d1_ny/USA500IDXUSD/year=*/` — full-day NY D1 bars built earlier, now unused.

## Next

Advance to ensemble candidate **#4: Donchian/channel breakout trend-follow** on a non-US-index instrument (DXY or oil). Separate branch, separate pre-reg.
