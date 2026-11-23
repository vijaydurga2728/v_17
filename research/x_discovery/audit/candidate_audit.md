# Candidate Audit — 11 X.com Strategies

**Date:** 2026-11-14
**Inputs:** X.com research report (pasted 2026-11-14), `source_verification.md`, v17 repo state on branch `cycle6-spx-led-fx`.
**Rule:** author claims and independent findings are kept in separate columns. Screenshots and win rates are not evidence.

## Summary table

| # | Candidate | Rules deterministic? | Independent replication | Audit grade | X report grade |
|---|---|---|---|---|---|
| 1 | ORB stocks-in-play | Mostly (ATR stop fraction unverified) | Yes on stocks (QuantConnect); index CFD version net zero (Krueger) | **A− on US stocks / D for our universe** | A− |
| 2 | Noise Area SPY | Mostly (gap adjustment unverified) | None | **B** | B |
| 3 | EWMAC | Yes (book + QC re-creation) | Yes (QC) | **A−** | A− |
| 4 | GEM | Yes | Yes, weakens claim | **A (negative)** | A |
| 5 | IBS QQQ | Yes | None | **C** | C |
| 6 | NR7 | No (window ambiguous, hidden parameter) | None | **C−** | C |
| 7 | Market intraday momentum | Yes | Yes (Baltussen et al.; Li et al.); QC weaker | **A−** (upgraded) | B |
| 8 | RSI2 ES/NQ | Yes | Weak (CXO, 12 trades) | **C** | C |
| 9 | Silver Bullet | No | None; v17 own test failed | **D** | D |
| 10 | 80% rule | No (discretionary last step) | Anecdotal, ~62% not 80% | **D+** | C− |
| 11 | IB iFVG | No (closed indicator) | None | **D** | D |

Grade change versus the X report: **#7 upgraded B → A−.** The X report graded the tweet summary, but the underlying JFE paper has independent peer-reviewed confirmations across futures markets. **#1 split:** the grade only holds for the stock universe we cannot trade.

---

## 1. Concretum ORB on Stocks in Play
- **Author claims:** >1,600% net 2016–2023, Sharpe 2.81 (top-20 portfolio).
- **Independent:** QuantConnect Sharpe 2.4 on a smaller universe; forum users report live selection mismatch and stop-placement bugs. Krueger: the *index* ORB (Zarattini & Aziz, SSRN 4416622) on NQ/SPX/Dow/DAX/FTSE CFDs 2015–2026 is gross +0.13 R on NQ but **net +0.002 R (t 0.0)**; four of five markets net negative.
- **Concretum's own 2026 claim (X report, not verified):** plain 5-min ORB on SPY ≈ 1.0% CAGR net.
- **Missing:** exact ATR stop fraction; 2026 filter set (paywalled).
- **Deterministic?** Yes for the QC version.
- **Key weakness for us:** the edge is stock selection by relative volume. No stock universe, no exchange volume. On indices the rule is a different strategy and the independent test says net zero.

## 2. Noise Area (Beat the Market)
- **Author claims:** 19.6%/yr net, Sharpe 1.33, 2007–2024, in-sample. Lost 12.8% in 2016. 90-day lookback beat 14-day in the author's own table (sensitivity).
- **Independent:** none found. TradingView and user QC ports have no verified results.
- **Missing:** gap-adjustment formula.
- **Deterministic?** Yes once the paper's gap rule is read.
- **Sizing:** 2% daily vol target, up to 4× leverage. FTMO 0.5% risk-per-trade needs a stop-based translation; stop = band or VWAP.
- **Key weakness:** single author group, in-sample, lookback sensitivity, CFD spread.

## 3. EWMAC (Carver)
- **Independent:** QuantConnect re-created AFTS strategy #12 (EMAC 2/8 … 64/256, scalars, ±20 cap, FDM).
- **Author claims (books):** positive Sharpe across a large futures universe over decades.
- **Known weaknesses:** sideways markets; cost drag from fast speeds; edge comes mostly from diversification across 30–100 uncorrelated markets.
- **Deterministic?** Yes.
- **Key weakness for us:** 9 instruments, mostly USD-correlated (6 USD FX pairs + 3 US indices). v17 already saw TSM PF 1.03–1.23 and Donchian PF 0.78–1.07 on 3 of them in 4B.

## 4. GEM (Antonacci)
- **Independent:** ReSolve tested 1,226 variants; specification risk is large and uncompensated. Newfound reports fragility.
- **Not verified this session:** the "61%" and median-reversion figures in the X report.
- **Deterministic?** Yes.
- **Key weakness:** the independent work argues the original setting is luck. The instruments needed (bonds, ex-US equities) are outside the user's universe.

## 5. IBS < 0.1 on QQQ
- **Author claim only.** No costs, period or drawdown. Equity curve image only.
- **Deterministic?** Yes.
- **Weakness:** no evidence; signal overlaps RSI(2) < 10 on the same instrument as the live demo.

## 6. NR7
- **Author claim only.** Window wording contradicts the standard NR7. Instrument implied. Hidden parameter.
- **Deterministic?** No, until the author's definition is pinned down.

## 7. Market Intraday Momentum (Gao, Han, Li, Zhou 2018)
- **Peer-reviewed:** JFE 129(2). SPY 1993–2013. In-paper out-of-sample R² 1.2%. Stronger on high-volume, high-volatility and macro-news days.
- **Independent:** Baltussen, Da, Lammers, Martens (futures 1974–2020: intraday momentum across markets); Li, Sakkas, Urquhart (12 of 16 markets).
- **Contradicting:** QuantConnect tutorial: "lower returns over our testing period". Rosa (2022) finds a *different* predictor (overnight return) fails out of sample.
- **Not verified:** 6.67%/yr, Sharpe 1.08.
- **Deterministic?** Yes: sign of r(prev close → 10:00 ET); hold 15:30 → 16:00 ET.
- **Key weakness:** small per-trade edge (R² ~1–2%). The 30-minute hold means one spread per day against a small expected move. Post-2013 net-of-cost evidence on retail CFDs is not established.

## 8. RSI(2) Dip Buy on ES/NQ (Milk Man)
- **Author claims:** 83% WR, PF 2.53 since 2022. Flat 2018–2021. Fixed-contract equity curve inflates with index level. An unexplained "catch".
- **Independent:** CXO out-of-sample on SPY, 12 trades 2007–2009, mixed.
- **Deterministic?** Yes.
- **Key point:** this is our live RSI2-NAS100 plus a 200-day SMA filter and an RSI > 70 exit. It is a parameter adjustment, not a discovery.

## 9. ICT Silver Bullet / gap midpoint
- **Author claim only.** "Dealing Range" undefined; 70% unsourced; no stop or sizing.
- v17 cycle 1 already ran a frozen SB rulebook: PF 0.67.

## 10. Market Profile 80% Rule
- **Practitioner heuristic** (Dalton). Forum backtest ~62%. Rule definitions vary.
- **Deterministic?** No: footprint confirmation is discretionary. Even without it, the base-rate comparison (fill after *any* open outside value) has never been reported.

## 11. Initial Balance iFVG
- Closed indicator, video-only results. Untestable.

---

## Step 4 — Priority candidates: what would need to change to test on our instruments

### P1. Concretum ORB
| Change | Effect |
|---|---|
| Stocks → NAS100/US500/US30 CFD | Removes the relative-volume selection, which is the source of the edge. Becomes the plain index ORB. |
| Exchange volume → none | Relative volume impossible on a single index. |
| Spread | Krueger shows CFD spread ≈ the gross edge. |
| **Conclusion** | **Not transferable.** The testable version is the one already shown net zero, and it is the mirror of our shelved ORB fade. |

### P2. Carver EWMAC
| Change | Effect |
|---|---|
| 30–100 futures → 9 CFDs (6 FX + 3 US indices) | Much lower diversification. Expected Sharpe falls roughly with √(effective number of independent bets). |
| Futures roll → CFD swap | Must model daily financing; can be large on index CFDs held long. |
| Continuous position | FTMO trades in lots; position rounding (0.01 lot) adds buffering noise. Overnight and weekend holding rules on the FTMO account type **must be checked** (not verified). |
| Risk unit | Carver vol-targets the portfolio. FTMO 0.5%/trade risk does not map to a continuous system. A spec must define risk as portfolio vol target + FTMO daily/total loss breakers. |
| **Conclusion** | Testable on D1 data already on disk. It is the pre-announced extension of the 4B trend tests, so it counts against the trend family's multiple-testing budget. |

### P3. Noise Area intraday momentum
| Change | Effect |
|---|---|
| SPY → USA500IDXUSD cash-session M1 | Need DST-aware 09:30–16:00 ET bars, US holidays, half-days. |
| SPY volume → tick volume for VWAP | Trailing stop changes slightly; `compute_session_vwap` already has typical-price fallback. |
| 4× vol-targeted sizing → 0.5% risk per trade | Stop distance = entry to band/VWAP. Trade count unchanged; return scale changes. |
| Costs | Paper: $0.0035/share + $0.001 slippage. CFD: bid/ask from data. Must report gross and net, like Krueger. |
| Lookback | Freeze 14 days (paper base case). Do **not** pick 90 days because the author's table shows it is better. |
| **Conclusion** | Testable. No independent replication exists, so a v17 test would itself be the first independent check. |

### P4. RSI(2) ES/NQ
| Change | Effect |
|---|---|
| ES/NQ → NAS100 | Already done: it is the live demo strategy. |
| Add 200-day SMA filter, RSI > 70 exit | Changes the frozen demo rules after holdout was seen. Fifth p-hack layer. |
| Apply unchanged demo rules to US500/US30 | Legitimate cross-instrument check, but US500/NAS100 correlation is high, so it is weak confirmation. |
| **Conclusion** | **Reject as a new candidate.** Optional: run the frozen RSI2 rules on US30 (never-touched data) as a robustness check, after the demo ends 2026-12-11. |
