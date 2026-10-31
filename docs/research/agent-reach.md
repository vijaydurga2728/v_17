# agent-reach: ICT/SMC resources — substance extraction

Scope: 16 GitHub repos + 4 YouTube transcripts fetched. 6 YouTube videos were rate-limited (HTTP 429) and were not retried per skill rules. Metadata and READMEs are archived under `docs/research/raw/`.

Caveat: claimed backtest numbers from repo READMEs are not independently verified. Treat them as prior art, not evidence.

---

## Repo-by-repo

### 1. joshyattridge/smart-money-concepts — MIT, Python, PyPI `smartmoneyconcepts`
Pure indicator library. Public API: `smc.fvg(ohlc)`, `smc.swing_highs_lows`, `smc.bos_choch`, `smc.ob` (order block), `smc.liquidity`, `smc.previous_high_low`, `smc.sessions`, `smc.retracements`. Takes a lowercase-column OHLC(V) DataFrame. No bot, no backtest, no risk — just detection math. Updated 2026-04. Highly reusable as detection primitive layer — license permits.

### 2. SrsBlack/ict-knowledge-library — no license, Python, 226 concept files
Canonical, machine-readable ICT reference (2016–2026). Each concept has a markdown file with definition, formal criteria, formula, examples, common mistakes, cross-links, and a JSON block for RAG. Follows Karpathy LLM Wiki pattern. Directories: `01-market-structure/` (BOS, CHoCH, MSS), `02-liquidity/` (BSL, SSL, EQH/EQL, IRL/ERL, DOL). Reusable as spec source and glossary — no license means no code lift, but reading rights are implicit.

### 3 & 5. OPKYEI/ICT-Trading, dextergsm/ict-trading — no license, Python (fork pair)
ML-based ICT trading: XGBoost, Random Forest, Gradient Boosting, Logistic Regression. Claims 89–91% model accuracy, 65–70% winrate, Sharpe 2.0+, DD <15%. Multi-broker (OANDA, FTMO, Pepperstone, MT5). Uses Dukascopy CSV, multi-TF (1H/1D/1W), engineered features: MSS/BOS, OBs, FVGs, Breakers, Mitigation blocks, BSL/SSL, kill zones. Non-MVP for us (we agreed no ML), but useful architectural reference. Claimed numbers are suspicious — 89–91% model accuracy almost certainly overfit.

### 4. futureteck/ICT_Automated_Trading_System — no license, 455-byte README
Copilot-generated, hardcoded + ML variants planned. No results, no proof. Skip.

### 6. fallenpheonix23/ict-trading-bot — no license, Python, honest results
Best honest reference in the set. SPY 1h 2y: 40.3% winrate, PF 1.43, Sharpe 0.46, DD −16.4%, Total +17.6%. SPY+QQQ+GLD+TLT daily 15y: 52.1% winrate, PF 1.52, Sharpe 0.53, DD −5.12%, Calmar 1.22, β 0.008, +148% total, CAGR 6.25% vs SPY 13.65% buy-and-hold. Admits v1 lost 88% of capital. Fixes documented in DEVLOG.md: ATR-based stops (not fixed %), 50/200 EMA bias, OB displacement ≥2.0× ATR, MSS swing 10 bars with body >1.5× ATR, zone staleness, ADX>18 for longs / >25 for shorts, partial exit 1.5R → trail BE, idle T-bill return (biggest CAGR lift). Risk defaults: RISK_PCT=0.01, REWARD_R=2.0, PARTIAL_R=1.5, MAX_CONCURRENT=4, TXN=5bps. Steal the parameter set and the ATR stop logic.

### 7. islero/ICT-NT — MIT, Python 3.11+, Jupyter + Python
Framework on top of NautilusTrader. ICT + Turtle Soup. Rule-engine with modular rules: FVG, Smart Pivots, Liquidity Pools, Market Structure, Daily/Weekly Context, trailing SL, partial close, breakeven move, SMA exit, fixed-risk sizing, RR validation. Backtest on ESZ5 (E-mini). Clean CI (GitHub Actions). Reusable as architecture pattern for rule composition.

### 8. sixscripts-ai/train-ict — no license, Python, substantial
Deep ICT agent. `src/ict_agent/detectors/` has `fvg.py`, `order_block.py`, `market_structure.py`, `liquidity.py`, `displacement.py`. `src/ict_agent/models/` has `silver_bullet.py`, `judas_swing.py`, `power_of_three.py`, `turtle_soup.py`. Live execution via OANDA. Risk guardian module. Multi-TF HTF→ITF→LTF. `vex_brain_v2.py` is 76 KB main brain. No published results. Modular layout is the one closest to our MVP shape. Steal: directory structure + model definitions. License gap means we re-implement, not copy.

### 9. zakariab0/ozo — no license, Python + MT5
Direct MT5 integration via `MetaTrader5` pkg. Session detection (Tokyo/London/NY), candle/structure analysis, market+limit orders, liquidity sweep detection, news check via `beautifulsoup4` + `selenium`, bank holidays. No backtest results, no license. Reusable as pattern for MT5 adapter and session scheduler. Re-implement, do not copy.

### 10. Jakeschincariol/day-trader-skill — MIT, Python, Claude skills
11 Claude skills for US equities day trading (Yahoo + SEC EDGAR). Not ICT. Key idea to steal: `trader-timemachine` runs 10,000 Monte-Carlo replay sessions of the entry+exit rule on recent-session bars and historical pattern-fires. Direct analog to our planned MC validation. Also: `trader-risk`, `trader-budget`, `trader-exit`. Not forex, not MT5, but methodology maps.

### 11. nautechsystems/nautilus_trader — LGPL-3.0, Rust-core + Python
Production-grade event-driven engine. Deterministic. Rust performance, Python strategy API. No native MT5 broker adapter (uses Interactive Brokers, Binance, Databento, Betfair, Polymarket, Bybit, OKX, etc.). LGPL means linking is fine for closed-source Python strategies but any patches to the engine go back upstream. Overkill for MVP. Keep as fallback if MT5-via-Python latency/reliability fails.

### 12. mementum/backtrader — GPL-3.0, Python, mature but stale (last pushed 2024-08)
Classic Python backtest. GPL-3.0 is copyleft — using it as a library in our bot would force our bot to GPL. Skip for the live stack. Can use for throwaway research notebooks only.

### 13. Lumiwealth/lumibot — GPL-3.0, Python, AI-agent trading
Framework for AI agents (LLM) that call brokers. 12 brokers, forex supported. GPL contaminates. Skip for MVP. Pattern reference only.

### 14. freqtrade/freqtrade — GPL-3.0, Python, crypto only
Not forex. Skip.

### 15. TauricResearch/TradingAgents — Apache-2.0, Python, multi-agent LLM
Fundamental trading via a multi-agent LLM debate framework. Not ICT, not intraday scalping. Interesting pattern (planner/trader/risk-manager agents), out of MVP scope.

### 16. MobiusQuant/OpenMobius-skill — Apache-2.0, SKILL.md, 2008 knowledge cards
Multi-school trading knowledge skill (ICT/SMC default, ChanLun, Wyckoff, PA, Order Flow, VSA, Elliott) for Claude Code / Codex / Cursor / Hermes. Strict-mode ICT/SMC Q&A with Playwright + lightweight-charts rendering, nomic-embed-text-v1.5 vectors, cited rules. Not an executor. Reusable as live documentation/explain layer and as high-fidelity ICT reference during development.

---

## ICT rules consolidated from video transcripts

Transcripts fetched: `2G93Ypq4kG4` (ICT 90-day strategy), `k22dBXDk980` (intraday top-5), `tvERE-Beu2U` (Fabio Valentina, Robins futures champion), `5HLDy_masCk` (short, non-English). The 6 videos that returned HTTP 429 were not retried; sampling was intentionally kept to the limit the platform tolerated.

**London killzone timing (ICT canon, consistent across sources):**
- London killzone: 02:00–05:00 New York time (07:00–10:00 London). London Silver Bullet: 03:00–04:00 NY.
- New York killzone 1 (AM): 09:30–11:00 NY. NY Silver Bullet (AM): 10:00–11:00 NY.
- Judas Swing: first manipulation move of a session, typically within the first hour after open, sweeping Asian range high or low.

**Rule chain from `2G93Ypq4kG4` (ICT direct, applied to NY session; same shape applies to London):**
1. Mark the killzone window (9:30–11:00 NY in that video; for us, London 02:00–05:00 NY).
2. Pre-session, mark 5-minute BSL and SSL swings — the liquidity price can run.
3. Wait for buy-side or sell-side liquidity to be swept (ICT: `BSL raid` / `SSL raid`).
4. Drop to 1-minute. Mark the current valid swing and the displacement candle after the sweep.
5. Wait for a 1-minute market structure shift (MSS) in the opposite direction of the sweep.
6. Enter on the retracement into an unmitigated 1m FVG (optionally inside a 15m OB).

**Entry confluence stack we agreed on (BSL/SSL sweep → MSS → FVG inside OB) matches rule chain above exactly.**

**Fabio Valentina (`tvERE-Beu2U`) adds a cross-check we should encode:**
- 90% of traders chase MSS/BOS/CHoCH *after* it appears. His edge is anticipating the manipulation move that *creates* the sweep. Operationally: do not enter on the first MSS of the session; require that MSS to be preceded by a confirmed liquidity grab of the pre-session high or low. We already enforce this (Q4 answer C).
- Multi-TF stacks he uses: 15m/3m/1m or 1h/5m/1m. Compatible with our Daily+4H bias / 15m setup / 1m entry.
- Scaling: builds profit intraday, swings size up on directional days only. Not an MVP concern; log for later.

**FVG definition (joshyattridge canonical, matches videos):**
Bullish FVG = `low[i] > high[i-2]` with `close[i-1] > open[i-1]`. Bearish FVG = `high[i] < low[i-2]` with `close[i-1] < open[i-1]`. The gap is the imbalance between candle i−2 and candle i.

**Order Block definition (fallenpheonix23 + sixscripts converge):**
Bullish OB = last bearish candle before a bullish displacement move. Displacement threshold: body > 1.5–2.0× ATR, body ratio > 60%.

**MSS definition (fallenpheonix23 fixed set):**
Swing lookback 10 bars, break body > 1.5× ATR. Discard FVG/OB zones older than `MAX_ZONE_AGE = 30` bars.

**Risk defaults consistent across honest references:**
1% per trade, min 1:1.5 RR for partial, full target 2R. ATR-based stop with 1.0× ATR buffer below/above the zone edge; 0.5% minimum stop floor. These align with our FTMO Challenge $100k constraints.

Rate limit note: `5g3nGHlhpv0`, `AYO62d__Bog`, `GMSMMXz8iBg`, `PL7LKUsCgIQ`, `jvzd7UPlb5Y`, `nLQhKkjkuWI` returned `RATE_LIMITED` (HTTP 429). Not retried.

---

## Top 5 reusable artifacts (ranked)

1. **`joshyattridge/smart-money-concepts`** — the whole package. MIT. `pip install smartmoneyconcepts`. Use `smc.fvg`, `smc.swing_highs_lows`, `smc.bos_choch`, `smc.ob`, `smc.liquidity`, `smc.sessions` as our detection primitives on 15m and 1m DataFrames. Saves weeks.
2. **`fallenpheonix23/ict-trading-bot/ict_structures.py` + `ict_backtest.py`** — read-only, re-implement. Specifically: ATR-based stop with ATR_STOP_BUFFER=1.0 and MIN_STOP_PCT=0.005, OB displacement ≥ 2.0× ATR, MSS swing=10 bars body>1.5×ATR, zone staleness MAX_ZONE_AGE=30, partial exit at 1.5R and trail to BE, ADX filter 18 long / 25 short.
3. **`sixscripts-ai/train-ict/src/ict_agent/models/silver_bullet.py` and `judas_swing.py`** — re-implement, do not copy (no license). Use as reference for model entry+exit rule shape and multi-TF signal assembly.
4. **`zakariab0/ozo/*`** — re-implement MT5 session scheduler, order send/modify/close, bank-holiday + news gates (ozo uses selenium for FF; we will use the FF JSON feed instead).
5. **`SrsBlack/ict-knowledge-library/concepts/01-market-structure/` and `02-liquidity/`** — read-only canonical rule reference during spec writing (Phase 2). Pair with `MobiusQuant/OpenMobius-skill` for interactive clarification during build.

---

Report file: `C:\personal\v_17\docs\research\agent-reach.md`
Raw dumps: `C:\personal\v_17\docs\research\raw\`
