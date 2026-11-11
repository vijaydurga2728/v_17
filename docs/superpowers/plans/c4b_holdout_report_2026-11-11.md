# RSI2-USATECHIDXUSD Sealed-Holdout Report — 2026-11-11

**Window:** 2025-01-01 -> 2026-10-18 (D1 bars).
**Rules:** locked verbatim from C4B-S5 commit `1465ef3`. No param changes.
**Status:** GATE-LIMITED ADVANCE per `2026-11-11-cycle4b-mcpt-scheme-addendum.md`.

## Results

- Trades submitted: **29**
- Trades executed (post-breaker): **29**
- Trades rejected by breaker: **0**
- PF: **4.895** (require >= 1.3: PASS)
- Win rate: **75.9%** (require >= 50%: PASS)
- Max DD (R-cumulative): **8.66** (require < 10R: PASS)
- Hard-freeze triggered: **False** (require False: PASS)

## Verdict: HOLDOUT-PASS PRE-LIVE

## Caveats (binding)

- Even a HOLDOUT-PASS result is **NOT DEPLOY**. Live money is barred until:
  1. Scheme-1 MCPT is built (signal-time permutation with engine re-run).
  2. RSI2-NAS100 passes scheme-1 MCPT at p_pf < 0.05 single-pair (no Bonferroni).
  3. 90-day free demo follows per `user_trading_goals.md`.
- Compound end-to-end prior (holdout pass + scheme-1 pass + demo + FTMO + payout): 5-10%.