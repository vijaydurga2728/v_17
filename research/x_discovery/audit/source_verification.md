# Source Verification — X.com Discovery Report

**Date:** 2026-11-14
**Scope:** Verify the 11 candidates in the X.com research report against primary and independent sources.
**Method:** Web search plus one direct page fetch (MQL5 ORB replication). Primary PDFs were NOT opened in this session (SSRN/Elsevier). Every "rule" quoted here from a secondary summary is marked as such.

Legend:
- **Author claim**: stated only by the strategy's originator or vendor.
- **Independent**: a third party re-ran or re-implemented the rules and published results.
- **Not verified**: I could not reach the source this session.

---

## 1. Concretum ORB on "Stocks in Play"

| Item | Status | Source |
|---|---|---|
| Paper exists | Verified | Zarattini, Barbon, Aziz, "A Profitable Day Trading Strategy For The U.S. Equity Market", SSRN 4729284, Swiss Finance Institute RP 24-98 (https://ideas.repec.org/p/chf/rpseri/rp2498.html) |
| Sample: >7,000 US stocks, 2016–2023 | Verified (abstract) | https://concretumgroup.com/a-profitable-day-trading-strategy-for-the-u-s-equity-market/ |
| Top-20 stocks in play: >1,600% net, Sharpe 2.81, alpha 36%/yr | **Author claim** | same |
| Relative-volume rule (first 5 min ÷ 14-day avg first 5 min) | Independent | QuantConnect research #18444 (https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/) |
| QuantConnect Sharpe 2.4, beta ≈ 0 | Independent, smaller universe (500–1,500 stocks) | same |
| X report says QC replication "only covered 2016" | **Not confirmed**; QC page describes a parameter sweep over universe size; period not verified this session | — |
| Live-vs-backtest selection mismatch; stop orders placed incorrectly in IBKR paper | Independent (forum users) | QC forum #18444 p3 comments |
| Exact ATR stop fraction | **Not verified** (PDF not opened) | — |

**Related, decisive for our universe:** Krueger (MQL5 blog, 2026-09-25, https://www.mql5.com/en/blogs/post/776235) replicated the *index* ORB paper (Zarattini & Aziz, "Can Day Trading Really Be Profitable?", SSRN 4416622) on NQ, SPX, Dow, DAX, FTSE **CFDs**, Jan 2015 – Jun 2026, rules unchanged:
- Gross reproduced: NQ +0.131 R/trade (t 2.9), SPX +0.119 R (t 2.4).
- **Net of spread: NQ +0.002 R (t 0.0), SPX −0.081 R, Dow −0.081 R. Four of five markets negative.**
- 2021–2026 out of sample: "+0.06 R on NQ at best" (gross).
- Caveat: author sells MQL5 products. Treat as independent but promotional. Full study at kruegeralgorithms.com was not fetched.

## 2. SPY Intraday Momentum ("Noise Area", Beat the Market)

| Item | Status | Source |
|---|---|---|
| Paper exists | Verified | Zarattini, Aziz, Barbon, "Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)", SSRN 4824172, SFI RP 24-97 |
| 2007–2024, 1-min SPY | Verified (abstract/summaries) | https://www.sfi.ch/fr/publications/n-24-97-beat-the-market-an-effective-intraday-momentum-strategy-for-s-p500-etf-spy |
| 1,985% total, 19.6%/yr net, Sharpe 1.33 | **Author claim, in-sample** (CXO Advisory also calls it in-sample) | https://www.cxoadvisory.com/?p=45565 |
| Boundaries from open × 14-day avg move by minute; checks at HH:00/HH:30; VWAP trailing stop | Secondary summaries agree (CXO, QuantConnect-hosted backtest citing QuantPedia) | — |
| Gap-adjustment formula | **Not verified** (PDF not opened) | — |
| Independent replication | **None found.** Only a TradingView port and a user-posted QuantConnect conversion, neither with verified results | — |

## 3. Carver EWMAC Trend Following

| Item | Status | Source |
|---|---|---|
| EWMAC(2,8)…(64,256), forecast scalar, cap ±20, FDM to average 10 | Independent re-creation of strategy #12 from *Advanced Futures Trading Strategies* | https://www.quantconnect.com/research/15959/adjusted-trend-on-futures/ |
| Per-span forecast scalars (e.g. 1.91 for 64-span, 12.1 for 2-span) | Independent (QuantConnect) | same |
| ±20 cap rationale | Book table, reported second-hand | https://the7circles.uk/?p=24066 |
| "More speeds raised costs and lowered risk-adjusted returns" (X report) | **Not confirmed this session**; plausible from QC page, not quoted directly | — |
| Full rules | Carver's books + open-source `pysystemtrade` (not checked this session) | — |

## 4. GEM (Antonacci)

| Item | Status | Source |
|---|---|---|
| Rules (12-month absolute + relative momentum, US/ex-US/bonds) | Verified | ReSolve, "Global Equity Momentum: A Craftsman's Perspective" (2019) |
| 1,226 variants tested | Verified | https://hedgefundalpha.com/strategies/global-equity-momentum-a-craftsmans-perspective/ |
| "Specification risk is large and uncompensated" | Verified (ReSolve) | same |
| "Beat 61% of variants"; median reversion 1950–73 / 2012–18 | **Not verified this session** (figures not in search results) | — |
| Contrary view: robust across parameters | AlgoEdge Insights (blog, weaker) | — |
| Fragility case study | Newfound Research | https://blog.thinknewfound.com/tag/gem/ |

## 5. IBS Mean Reversion on QQQ — QuantifiedStrategies
Author claim only. Single equity-curve image. No costs, no period, no drawdown. **No independent test found.**

## 6. NR7 Compression — QuantifiedStrategies
Author claim only. Rule definition ambiguous (6 vs 7 days). Instrument implied. Undisclosed "one parameter" improvement. **No independent test found** this session (NR7 is a Crabel/Connors concept, but this specific rule set is unverified).

## 7. Market Intraday Momentum (Gao, Han, Li, Zhou)

| Item | Status | Source |
|---|---|---|
| Published, peer-reviewed | Verified | *Journal of Financial Economics* 129(2), 2018, pp. 394–414 (https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414) |
| SPY, 1993–2013; first half-hour (prev close → 10:00 ET) predicts last half-hour | Verified (abstract) | same |
| In-paper out-of-sample R² 1.2% | Verified (paper excerpt in search) | https://www3.nd.edu/~zda/intramom.pdf |
| 6.67%/yr, Sharpe 1.08 | **Not verified this session** (quoted via QuantifiedStrategies) | — |
| Independent: Baltussen, Da, Lammers, Martens — intraday momentum across futures, 1974–2020 | Independent, peer-reviewed | Notre Dame working paper (https://www3.nd.edu/~zda/EOD.pdf) |
| Independent: Li, Sakkas, Urquhart — predictability in 12 of 16 markets | Independent | Nottingham repository |
| QuantConnect "Intraday ETF Momentum" tutorial: "lower returns over our testing period" | **Independent, weaker result** | https://www.quantconnect.com/learning/articles/investment-strategy-library/intraday-etf-momentum |
| Rosa (2022, J. Futures Markets): overnight-return variant disappears out of sample | Independent, **different predictor** | https://ideas.repec.org/a/wly/jfutmk/v42y2022i12p2218-2234.html |

## 8. RSI(2) Dip Buy on ES/NQ — The Milk Man
Author claim only (83% WR, PF 2.53 since 2022). Rules credited to Connors/Alvarez. Underlying Connors RSI(2) has weak independent evidence: CXO Advisory out-of-sample test on SPY 2007–2009 found 12 trades, "mixed" (https://www.cxoadvisory.com/technical-trading/out-of-sample-tests-of-bullish-regime-2-day-rsi-signals). Other "still works" claims are vendor posts.

## 9. ICT Silver Bullet / Gap Midpoint
Author claim only. "Dealing Range" undefined. 70% figure unsourced. **No independent test.** v17 already tested a frozen SB rulebook (cycle 1, PF 0.67).

## 10. Market Profile "80% Rule"
Origin: Dalton, *The Profile Reports* (1987–1991). No formal statistical study found. A forum TradeStation test reported ~62% completion, not 80% (NexusFi). A NexusFi article reports the figure "dissolves under rigorous testing". Rule definitions vary between sources. Final entry step ("buyers holding on the footprint") is discretionary.

## 11. Initial Balance iFVG — Herman Trading
Direction comes from a closed proprietary indicator. Results shown only in video. **Untestable.**

---

## Summary

| # | Independent replication exists? | Replication direction |
|---|---|---|
| 1 ORB stocks-in-play | Yes (QuantConnect) | Supports, on US stocks |
| 1b ORB on index CFDs | Yes (Krueger) | **Net zero after spread** |
| 2 Noise Area | No | — |
| 3 EWMAC | Yes (QuantConnect) | Supports concept; cost sensitivity |
| 4 GEM | Yes (ReSolve, Newfound) | **Weakens** the original claim |
| 5 IBS | No | — |
| 6 NR7 | No | — |
| 7 Intraday momentum | Yes (Baltussen et al.; Li et al.; QuantConnect) | Mostly supports; QC weaker |
| 8 RSI2 ES/NQ | Weak (CXO, tiny sample) | Mixed |
| 9 Silver Bullet | No | v17 own test: fail |
| 10 80% rule | Anecdotal | Weakens (~62%) |
| 11 IB iFVG | No | — |
