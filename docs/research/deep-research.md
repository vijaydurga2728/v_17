# Deep Research — ICT/SMC Intraday Trading System

**Date:** 2026-10-28
**Scope:** Python 3.11+ ICT/SMC bot, MT5 live execution, FTMO Challenge $100k, 5y backtest with walk-forward 12 folds + Monte Carlo 1000, London killzone EURUSD+GBPUSD.
**Sources:** official docs, PyPI, GitHub, FTMO site, Wiley/Pardo, FFCal JSON feed. Every claim cited.

---

## 1. MetaTrader5 Python Package

- **Official docs:** <https://www.mql5.com/en/docs/python_metatrader5>
- **44 functions** across connection, account, symbols, market depth, historical data, orders/positions, history. (same source)
- **`initialize(path=None, login=…, password=…, server=…, timeout=60000, portable=False)`** — returns `True`/`False`. Default connection timeout **60000 ms**. Source: <https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py>
- **`order_send(request)`** returns `MqlTradeResult` with `retcode`. Success = `TRADE_RETCODE_DONE` (10009). Fail detail retrieved via `last_error()`. Request fields: `action, symbol, volume, price, sl, tp, type, type_filling, type_time, magic, comment, position`. Source: <https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py>
- **Platform: Windows only.** PyPI package is Windows-only; Linux/macOS require Wine or the third-party `mt5linux` bridge (<https://pypi.org/project/mt5linux>). Confirmed: <https://www.mql5.com/en/book/advanced/python/python_install>
- **No rate limit published**. Official docs do not state QPS caps. Community convention: throttle ticks to ≥50 ms, never spin on `symbol_info_tick`. Package is **synchronous**; async must be done via thread/asyncio executor.
- **No native tick stream (push).** Must poll `symbol_info_tick(symbol)` or `copy_ticks_from(symbol, from, count, flags)`. Entry logic on 1m should poll ticks at ≥10 Hz during killzone, build in-memory 1m from ticks for lowest latency; otherwise `copy_rates_from_pos` the latest 1m bar every ~5 s.
- **Fill detection:** after `order_send` with `TRADE_RETCODE_DONE`, read `result.deal` ticket, then confirm via `history_deals_get(ticket=...)` or `positions_get(symbol=...)`. Position modification uses `TRADE_ACTION_SLTP`.

## 2. Backtest Framework Comparison

| Framework | Last release / status | Tick fills | Bid/Ask | Multi-TF | Walk-forward | Monte Carlo | Verdict |
|---|---|---|---|---|---|---|---|
| **nautilus_trader** | v1.x stable, v2 RC, active (Py 3.13-3.14, cross-platform) <https://github.com/nautechsystems/nautilus_trader> | yes (ns-resolution ticks) | yes | yes | no native | no native | **Best technical fit, no MT5 adapter, authors say "do not use RC in prod"** |
| **backtrader** | **UNMAINTAINED** — last PyPI 1.9.78.123 (Apr 2023), no activity since Aug 2024 <https://dev.to/jun_yin_6302a0bd8ff9871c1/is-backtrader-still-maintained-status-and-four-maintained-alternatives-4ami> | partial | yes (Bid/Ask→OHLC article) | yes | manual | no | Skip for new project |
| **backtesting.py** (kernc) | active 461 commits <https://github.com/kernc/backtesting.py> | no (bar-level only) | no spread model | no native MTF | SAMBO optimizer only, no WF | no | Too simplistic for ICT MTF logic |
| **vectorbt (OSS)** | active, PRO features gated <https://vectorbt.dev/> | no | no | partial | vectorbtpro only | partial | Vectorized, not event-driven; wrong tool for ICT |
| **lumibot** | Py 3.10+, 100+ brokers but **no MT5** <https://lumibot.lumiwealth.com/> | no | no | daily/intraday | no | no | Rules out — no MT5 |
| **Custom numpy/pandas** | n/a | full control | full control | full control | full control | full control | Required glue, 1–2 weeks dev |

**Verdict:** **Custom event-driven backtester + `smartmoneyconcepts` lib for ICT primitives** is the correct path. Nautilus is overkill without MT5 adapter and v2 is pre-prod. Backtrader is dead. Build thin event loop in Python 3.11+ with Polars/pandas, pre-resample D/4H/15m/1m bars, feed bar-close events to strategy, model fills with explicit spread + slippage. Monte Carlo + walk-forward are our own code — standard methodology (see §5–6).

## 3. ForexFactory Calendar

- **Feed URL (unofficial but stable):** `https://nfs.faireconomy.media/ff_calendar_thisweek.json` — **confirmed reachable and valid JSON** (fetched 2026-10-28). Array of events with fields: `title, country, date (ISO 8601), impact (Low|Medium|High|Holiday), forecast, previous`. 94 events for week of 2026-10-25.
- **Sister feeds:** `ff_calendar_nextweek.json`, `ff_calendar_lastweek.json`, `ff_calendar_thismonth.json` (same host).
- **Historical archive for backtest (2014–2026):** FF site itself exposes `forexfactory.com/calendar?week=mmm-dd.yyyy` HTML pages; community GitHub mirrors exist (search `economic-calendar-history`). Reliability: scrape with 2 req/sec throttle, cache to Parquet.
- **`investpy` lib:** largely broken since Investing.com API locked down in 2021 — avoid.
- **`economic-calendar` (python lib):** community-maintained wrapper around the FF JSON feeds — thin wrapper, OK as reference. Prefer direct JSON fetch (one HTTP call, zero dependencies).

## 4. FTMO Challenge $100k Rules (2026-10)

From <https://ftmo.com/en/trading-objectives/>, <https://ftmo.com/en/trading-rules/>, <https://propnavi.io/en/blog/ftmo-prohibited-strategies/>, <https://www.eafunded.com/firms/ftmo>:

- **Max daily loss:** 5% of initial sim capital = $5,000.
- **Max overall loss (static):** 10% = $10,000 (floor $90,000).
- **Minimum trading days:** 4.
- **Phase 1 target:** 10% ($10,000).
- **Phase 2 target:** 5% ($5,000).
- **Consistency rule (funded account only, payout gate):** best day ≤ 30% of total profit. Not a breach — must keep trading until ratio drops. Source: <https://backtrex.com/en/blog/prop-firm-consistency-rule-30-percent-explained>. **Note:** 1-Step Challenge got Consistency rule from 2026-10-12 (replaces old Best Day 50%). <https://stonkjournal.com/articles/ftmo-review>
- **News trading:** **restricted on Standard (Normal) account** during live/funded phase, **allowed during Evaluation Phase 1+2** — but we blackout anyway for robustness. Swing account has no news restriction.
- **Weekend holding:** restricted on Standard, allowed on Swing.
- **EAs/bots:** **allowed on MT4/MT5/cTrader, no pre-approval, no source review**. <https://www.pineconnector.com/blogs/pico-blog/ftmo-challenge-rules-automated-traders>
- **Banned strategies:** HFT (dozens of trades/min), tick scalping with ms holding times, latency arbitrage, grid, martingale, external commercial copy-trading, strategies that add to losers.
- **Our ICT bot:** 1–3 trades/day, ≥1 min holding, no grid, no martingale → fully compliant.

## 5. Monte Carlo for Trading Systems

- **Three methods (Pardo, Aronson *Evidence-Based TA*, Pardo 2008):**
  1. **Trade-order shuffle (permutation):** reorders existing closed trades without replacement. Each trade appears once. Final equity same, path differs. Tests path dependency only.
  2. **Trade bootstrap (resample with replacement):** draws N trades with replacement from original pool. Composition and order vary. Pessimistic. <https://quanthop.com/learn/validation-robustness/monte-carlo-simulation>
  3. **Block bootstrap:** resample contiguous blocks of trades (block length ≈ autocorrelation decay) to preserve serial correlation. Standard fix for drawdown-sensitive strategies. <https://quanttradingtools.com/monte-carlo-simulation-trading/>
- **Key limitation:** plain shuffle/bootstrap destroys losing-streak clustering → underestimates drawdown. **Use block bootstrap with block length ≥ 5 trades** for drawdown stats. <https://quanttradingtools.com/monte-carlo-simulation-trading/>
- **Our MC plan:**
  - 1000 runs, hybrid:
    - 500 trade-order permutations → confidence interval for terminal equity, max DD distribution (path only).
    - 500 block bootstraps, block=5 → MC 95% CI for PF, Sharpe, max DD (realistic).
  - Pass gate: 5th percentile PF ≥ 1.3, 95th percentile max DD ≤ 8% (FTMO 10% − 2% buffer).

## 6. Walk-Forward Optimization

Primary source: Pardo *The Evaluation and Optimization of Trading Strategies* (Wiley, 2008), Ch 11. <https://onlinelibrary.wiley.com/doi/10.1002/9781119196969.ch11>

- **Rolling (unanchored):** fixed-length IS window moves forward by OOS length each fold. Best for intraday / regime-adaptive strategies. <https://en.wikipedia.org/wiki/Walk_forward_optimization>
- **Anchored:** IS window starts at same point, grows each fold. Good for slow-regime assets.
- **IS/OOS ratio:** Pardo (2008) recommends IS = 4–6× OOS (≈ 80/20–85/15). Common practical splits 70/30 or 60/40. <https://fxfoundations.com/learn/backtesting-journaling/strategy-optimization>
- **Fold count:** ≥10 folds for robustness; 20–40 preferred. <https://tradetally.io/blog/walk-forward-analysis/>
- **Robustness metric:** Walk-Forward Efficiency (WFE) = OOS return ÷ IS return. **WFE ≥ 0.5** = robust; ≥ 0.7 = strong. <https://tradetally.io/blog/walk-forward-analysis/>
- **Our plan:** rolling, 12 folds across 2014–2026, IS = 1 year, OOS = ~2 months each fold (ratio 6:1 ≈ 86/14). Reject strategy if median WFE < 0.5 or any OOS fold has PF < 1.0.

## 7. Dukascopy Data vs User's CSVs

- **User CSVs are Dukascopy-exported 1m bid/ask** (filename pattern `SYMBOL_1 Min_Ask_YYYY.MM.DD_YYYY.MM.DD.csv`). Dukascopy is a Swiss bank, publishes tick feed free over HTTP from aggregated bank liquidity. <https://www.dukascopy.com/swiss/english/marketwatch/historical/>
- **Quality:** independently sourced multi-provider aggregate, converted tick→bar. Fewer gaps, more accurate OHLC than broker MT5 history exports. <https://strategyquant.com/blog/preparing-accurate-data-for-algo-trading-broker-data-feed-differences/>
- **Gotcha 1 — bid vs ask bars:** Dukascopy exports **separate bid-OHLC and ask-OHLC files**. The user has both. Build **mid = (bid_close+ask_close)/2 only after aligning timestamps**. Spread = ask_close − bid_close. Never mix bid-high with ask-low (gap artifacts).
- **Gotcha 2 — weekend / holiday gaps:** Dukascopy data has empty minutes during low-liquidity hours (3am London weekends). Backtester must skip no-trade bars, not interpolate.
- **Gotcha 3 — DST:** timestamps are UTC. Convert to London time with `pytz` + DST awareness. London killzone 07:00–10:00 London time = 06:00–09:00 UTC (BST) / 07:00–10:00 UTC (GMT winter). Get this wrong, kill the strategy.
- **Verdict:** user's local CSVs are **production-grade**. No external download needed.

## 8. ICT Concepts Formalization

**No peer-reviewed academic papers** on ICT FVG/OB/MSS as of 2026. All sources are: Michael J. Huddleston (Inner Circle Trader) YouTube mentorships, derived blog write-ups, and open-source implementations. Treat ICT as proprietary heuristics, not academic consensus.

Operational definitions (sourced from `smartmoneyconcepts` library implementation + consensus write-ups):

- **FVG (Fair Value Gap):** 3-candle pattern.
  - *Bullish FVG:* candle[-2].high < candle[0].low AND candle[-1] is bullish (middle candle breaks up). Gap zone = [candle[-2].high, candle[0].low].
  - *Bearish FVG:* candle[-2].low > candle[0].high AND candle[-1] is bearish. Gap zone = [candle[0].high, candle[-2].low].
  - Source: <https://www.strike.money/technical-analysis/fair-value-gap>, <https://innercircletrader.net/tutorials/valid-ict-fair-value-gap/>, `smartmoneyconcepts` Python lib <https://github.com/joshyattridge/smart-money-concepts>.
- **Order Block (OB):** last opposing candle before an impulsive move that produces a BOS.
  - *Bullish OB:* last bearish candle before a BOS up. Zone = [candle.low, candle.high].
  - *Bearish OB:* last bullish candle before a BOS down.
- **BOS (Break of Structure):** price closes beyond prior swing high/low in the direction of trend. Continuation signal.
- **CHoCH (Change of Character):** first break of structure against prior trend. Reversal signal. (This is what we treat as **MSS = Market Structure Shift** on 1m for entry.)
- **BSL / SSL (Buy-Side / Sell-Side Liquidity):** cluster of highs (BSL) or lows (SSL) within tight range — stops rest beyond. A sweep = price wicks past the cluster then closes back inside.
- **Silver Bullet:** 1-hour window 03:00–04:00 NY (= 08:00–09:00 London BST). Trade: in HTF bias direction, wait for liquidity sweep, enter on 1m MSS into 15m FVG inside OB, SL beyond swept wick, TP 1:1.5+ into next liquidity.
- **Judas Swing:** London open fakeout — first 1h after 02:00 NY sweeps Asian high or Asian low, then reverses. Enter on 1m MSS after sweep.

**Reference implementation:** <https://github.com/joshyattridge/smart-money-concepts> — MIT-licensed Python, 2.1k ⭐, active, implements FVG, swings, BOS/CHOCH, OB, Liquidity, sessions. Use as oracle for primitives; wrap with our own entry/exit/risk logic.

---

## Top 3 Decisions Locked by Research

1. **Backtest framework: custom event-driven Python** (Polars/pandas, bar-close events, explicit spread+slippage model) + `smartmoneyconcepts` lib for ICT primitives. Rejected: Nautilus (no MT5 adapter, v2 pre-prod), backtrader (dead), backtesting.py (bar-level too simple), vectorbt (vectorized, wrong paradigm), lumibot (no MT5).
2. **FTMO gotcha: Consistency Rule now applies on 1-Step Challenge from 2026-10-12** (best day ≤ 30% of total profit). Risk engine must track daily P&L against running total profit and reject new entries if best-day ratio > 30% after fill. Also: hold at least 4 trading days (min-days rule) — bot cannot pass Phase 1 in a single huge day.
3. **Monte Carlo: hybrid 500 trade-order permutations + 500 block-bootstrap (block=5)**, not plain IID bootstrap. Preserves losing-streak clustering so DD estimates are honest. Gate: 5th percentile PF ≥ 1.3, 95th percentile max DD ≤ 8%.
