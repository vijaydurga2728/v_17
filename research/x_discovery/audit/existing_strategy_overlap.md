# Existing Strategy Overlap

**Date:** 2026-11-14
**Purpose:** Stop variations of already-tested ideas from being counted as new discoveries.

## v17 research ledger (what has already been tested)

| Cycle | Family | Instrument / TF | Result | Record |
|---|---|---|---|---|
| 1 | ICT doctrine (Silver Bullet, 6 engines; 1 sampled) | EURUSD/GBPUSD/NAS100 M1 | SHELVED, PF 0.67, 25 trades | `GATE_MANIFEST.md` |
| 2 | ORB **fade** (30-min OR) | NAS100 M1 | SHELVED, PF 1.142 | `orb_dev_gate_report_2026-11-11.md` |
| 2b | ORB fade + D1 EMA20 trend filter (pre-reg rescue) | NAS100 M1 | SHELVED, PF 1.204 | `orb_trend_filter_prereg_2026-11-11.md` |
| 3 | Overnight gap **fade** | NAS100 M1 | SHELVED, PF 0.936 | `gap_dev_gate_report_2026-11-11.md` |
| 4 | TSM / Donchian / RSI2 symmetric, **H1** | EURUSD/GBPUSD/NAS100 | Failed smoke; rewritten (see `historical_recovery` in `candidate_decisions.md`) | commits `e57c370`, `57c9345`, `0fd08df` |
| 4B | TSM(252/21) / Donchian(20/10, 2N) / RSI2 long-only, **D1** | same 3 | 6 of 7 SHELVE; RSI2-NAS100 gate-limited advance → demo | `c4b_gate_report_2026-11-11.md` |
| 4B-x | RSI2 symmetric pooled, 8 FX majors D1 | FX D1 | Fisher p≈0.04 (optimistic, correlation ignored), sign flips → not advanced | commit `b0b46fa` |
| 5 | FX cointegration pairs (ADF, then rolling) | 28 FX pairs D1 | SHELVED; 0 holdout trades | commit `c047d20` |
| 6 | SPX VWAP regime → FX M5 pullback entry | AUDUSD/USDJPY M5, US500 regime | **In progress.** 28/48 grid configs done, all Sharpe < 0 (best −1.013) | `out/c6/dev_grid.progress` |

## Candidate-by-candidate classification

Categories (from the brief): **1** new family · **2** variation of existing · **3** parameter adjustment · **4** hypothesis already rejected · **5** untestable.

| # | Candidate | Nearest v17 work | Class | Reason |
|---|---|---|---|---|
| 1 | ORB stocks-in-play (continuation) | Cycle 2 ORB fade | **2** on indices / **1** on single stocks | On an index it is the mirror of the ORB fade. The edge in the paper comes from *stock selection by relative volume*, which needs a stock universe. Index version: independent CFD test is net zero (see source_verification §1). Note our ORB fade on NAS100 had PF 1.14 *gross-positive* — continuation and fade cannot both be net-positive on the same breakout; this is consistent with "no edge after costs". |
| 2 | Noise-Area intraday momentum | Cycle 6 used SPX VWAP as a *regime filter for FX*, never traded SPX itself | **1** (intraday index momentum) | No v17 cycle traded index intraday continuation to the close. Shares the VWAP primitive with cycle 6 but the hypothesis differs. Same family as #7. |
| 3 | EWMAC trend | Cycle 4B TSM + Donchian | **2** | Same trend-following family that failed in 4B on 3 instruments. Differences: continuous forecast, vol-targeted size, multiple speeds, multi-instrument portfolio. The 4B pre-reg (§3 S1) said in advance that TSM failure was partly due to the 3-instrument universe and "expanding universe later is the honest next move". So this is a **pre-announced extension**, not a fresh discovery. |
| 4 | GEM | Cycle 4B TSM (12-month lookback) | **2** + universe incompatible | Monthly absolute momentum = TSM(12) on equities + bonds switch. Needs bonds and ex-US equities, which the user excluded (4B pre-reg §3.5). |
| 5 | IBS < 0.1 on QQQ | RSI2-NAS100 (live demo) | **2** | Short-term dip-buy on the index's upward drift. Signals overlap heavily with RSI(2) < 10. Not independent of the demo strategy. |
| 6 | NR7 compression | none direct | **1** nominally, but long-only exit on close > prior high | Long-only index dip/compression buy also rides the drift that RSI2 rides. Rules ambiguous. |
| 7 | Market intraday momentum (first ½h → last ½h) | none | **1** (intraday index momentum) | Not tested in v17. Same family as #2; count #2 and #7 as **one family** for multiple-testing. |
| 8 | RSI(2) ES/NQ (Milk Man) | RSI2-NAS100 (live demo) | **3** | Same entry (RSI2 < 10). Differs by a 200-day SMA filter and an RSI > 70 exit (ours: close > SMA5, 10-day cap, **no 200-day filter**). Adding the filter now, after seeing dev+holdout, would be a fifth p-hack layer on the demo strategy. |
| 9 | ICT Silver Bullet / gap midpoint | Cycle 1 | **4** + **5** | Already rejected. "Dealing Range" undefined. |
| 10 | Market Profile 80% rule | ORB/Gap fade (mean reversion back into value) | **2**/**5** | Reversion-to-value on NAS100 intraday is the fade family that failed 3 times. Last step is discretionary. |
| 11 | IB iFVG | Cycle 1 (FVG primitives in `structure/fvg.py`) | **5** | Closed indicator decides direction. |

## Independent families actually on the table

After merging variations, the 11 candidates reduce to **4 testable families**, of which only one is new to v17:

1. **Intraday index momentum** (#2 Noise Area, #7 MIM) — **new to v17**.
2. Trend following, multi-instrument (#3 EWMAC, #4 GEM) — extension of a rejected family.
3. Short-term index dip-buy (#5 IBS, #6 NR7, #8 RSI2 ES/NQ) — same family as the live demo; not independent.
4. Opening-range continuation (#1) — needs a stock universe; index version already shown net zero.

Untestable or rejected: #9, #10, #11.
