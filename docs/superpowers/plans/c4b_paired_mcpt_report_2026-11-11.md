# RSI2-USATECHIDXUSD Paired-Alpha Scheme-1 MCPT Report — 2026-11-11

Independent-confirmation test alongside per-trade mean_r scheme-1.
Permutations: 500. Alpha: 0.05.

## Construction

- active_pos_t = 1 while in RSI(2) trade, 0 flat.
- exposure_frac = mean(active_pos).
- alpha_t = (active_pos_t - exposure_frac) * log_return_t.
- Null: random entry days, same count and avg_holding, same alpha formula.

## Dev window

- Observed: cum=0.58004 mean=0.000266 pf=1.200
- Trades 106, avg hold 3.5, exposure 0.170
- p_cum = **0.0060** (PASS)
- p_mean = **0.0060** (PASS)
- p_pf = 0.0100

## Holdout window

- Observed: cum=0.34196 mean=0.000614 pf=1.480
- Trades 29, avg hold 3.5, exposure 0.183
- p_cum = **0.0000** (PASS)
- p_mean = **0.0000** (PASS)
- p_pf = 0.0040

## Verdict

- Dev independent-confirmation pass: **True**
- Holdout independent-confirmation pass: **True**