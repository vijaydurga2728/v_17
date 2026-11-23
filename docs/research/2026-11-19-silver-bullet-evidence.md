# Silver Bullet — external evidence review (2026-11-19, for cycle 24 decision)

Sources gathered with the agent-reach skill (web, GitHub, Reddit search snippets; YouTube transcript rate-limited,
primary transcript read from a public mirror). Third-party numbers are as published, not re-verified by us.

## 1. ICT's own definition (2023 mentorship, "ICT Silver Bullet Time Based Trading Model", transcript)

- Windows (NY local): 03:00-04:00, 10:00-11:00, 14:00-15:00.
- First decide the draw on liquidity: previous day / session / week high or low, return to or expansion away from a
  current or old NWOG, OTE, or an inefficiency (FVG) above/below price.
- Inside the window a fair value gap forms; enter in the FVG toward the draw. Entry must be inside the window; the
  trade may be held after it.
- Framework: the move must *offer* >= 10 handles (indices) / 15 pips (FX); take >= 5 handles.
- No mandatory liquidity sweep, no mandatory 15 m MSS. Those are community overlays.
- ICT: "the main emphasis is determining the next most likely draw" — the discretionary part.

## 2. Mechanical backtests published by others

| Source | Rules | Data | Result |
|---|---|---|---|
| getalphacharts.com | 10-11, first 5 m FVG, limit at near edge, stop beyond candle 1, 2R, costs | MNQ 5 m, 2024-10..2026-10, 328 trades | PF 1.03, WR 36%; last 8 months negative |
| quantreplay.ai | Silver Bullet | MNQ 10 years | Out-of-sample PF 0.95, -0.03R/trade |
| thinridge.io | 10-11 FVG >= 2 pts, 60-min hold | NQ 1 m 2008-2026, 2,396 trades, costs | Net loss; 4,626/5,000 random-side copies did as well |
| wickcheck.com | sweep -> FVG -> limit, stop beyond sweep, next pool | NQ 5 m (Dukascopy) 12 months, 28 trades | PF 0.44, WR 18% |
| s4u.pro | windows + FVG | 2 indices, 16 years, 4,125 trades | PF 1.14, +0.099R/trade, max DD -86.8R, 39-loss streak |
| Reddit u/Familiar-Cry3355 | every FVG in AM window, 1:2 fixed | NQ M5 "last few years", 2,097 trades | +261R (~+0.12R/trade), WR 37%; costs unclear |
| Reddit u/ifeelichigo | strict sweep + MSS + FVG in one hour | ES/NQ/EURUSD 2025 | ES 3 trades, NQ 0, EURUSD 2; relaxed version PF 0.14/0.08 (crypto) |
| pinescriptforge.com | marketing "audit" | NQ, n=722 | PF 2.01 claimed — no method/out-of-sample disclosure, not credible |

## 3. Our own cycles (same conclusion)

| Cycle | Reading | Result |
|---|---|---|
| c17 | sweep-driven SB v2 | 0/12, PF 0.43-1.03 |
| c18 / c18b | ICT's own 2023 rules (DOL + FVG + 10 pt framework, no sweep) | 0/12 dev PF 0.41-0.85; holdout 2025-26 PF 0.53-0.97 |
| c19 | full sequence (DOL + PD + sweep + displacement + MSS + 2R) | 0-34 trades/slot, 0/12 |
| c20 | + SMT / OTE / IPDA | 2-23 trades/slot, 0/18 |
| c21 -> c23 | strict sweep + 15 m MSS + FVG | 0 trades in 7 years on NAS/SPX/US30 |

## 4. Conclusion

Across 8 external mechanical tests and 6 of ours, the Silver Bullet behaves the same way: strict readings almost never
fire; loose readings fire often and land between PF ~0.4 and ~1.15 after costs. The best credible positive (s4u.pro,
PF 1.14, -87R drawdown) is below a PF 1.30 gate and incompatible with FTMO drawdown limits. No public source shows a
robust, out-of-sample, after-cost PF >= 1.3. Whatever edge discretionary ICT traders report lies in the "next draw on
liquidity" judgement, which no published rule set captures.
