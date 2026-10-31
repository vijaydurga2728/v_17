# Find-Skills Report — ICT/SMC MT5 Trading Bot

Date: 2026-10-28
Scope: Python ICT/SMC intraday bot, MT5 execution, FTMO target, EURUSD+GBPUSD London killzone.
Threshold: 1K+ installs OR reputable source. Below-threshold entries kept only when no better option exists for a critical gap.

## Already installed — covers these needs

| Need | Covered by |
|---|---|
| ICT/SMC/Wyckoff/VSA concept Q&A | `openmobius-skill` |
| Python idioms + PEP 8 | `python-patterns` |
| Pytest/TDD/mocks/coverage | `python-testing` |
| Brainstorm, plan, spec, build, test, review, ship | `agent-skills:*` suite |
| TDD red-green-refactor | `superpowers:test-driven-development`, `mattpocock-skills:tdd` |
| Systematic debugging | `superpowers:systematic-debugging`, `mattpocock-skills:diagnosing-bugs` |
| Writing specs + implementation plans | `superpowers:writing-plans`, `agent-skills:spec` |
| Subagent-driven execution + verification gate | `superpowers:subagent-driven-development`, `superpowers:verification-before-completion` |
| ADR + docs | `agent-skills:documentation-and-adrs`, `mattpocock-skills:domain-modeling` |
| API/module boundary design | `agent-skills:api-and-interface-design`, `mattpocock-skills:codebase-design` |
| Security hardening | `agent-skills:security-and-hardening` |
| Observability + logging | `agent-skills:observability-and-instrumentation` |
| CI/CD | `agent-skills:ci-cd-and-automation` |
| Performance tuning | `agent-skills:performance-optimization` |
| Research primary sources | `mattpocock-skills:research` |
| Market/sentiment research (Reddit/YT/HN) | `last30days`, `agent-reach` |
| Minimal-diff coding discipline | `andrej-karpathy-skills:karpathy-guidelines`, `ponytail:*`, `caveman:lean-build`, `caveman:surgical-patch`, `caveman:verify-and-stop` |
| Telegram host channel (bot→me) | `telegram:configure`, `telegram:access` (NB: this is for Claude↔me, not for the trading bot to send alerts) |

## Marketplace candidates (ranked)

Threshold: 1K+ installs. Below-threshold rows marked `LOW` and only kept where no higher-install alternative exists.

| # | Skill | Installs | Fits | Install command |
|---|---|---|---|---|
| 1 | `tradermonty/claude-trading-skills@mt5-robot-tester` | 2.4K | MT5 EA/robot backtest harness guidance. Direct hit for our MT5 execution adapter + backtest tie-in. | `npx skills add tradermonty/claude-trading-skills@mt5-robot-tester -g -y` |
| 2 | `tradermonty/claude-trading-skills@economic-calendar-fetcher` | 3.5K | Scrape + parse economic calendar for high-impact news blackout. Direct hit for Q10 ±5 min filter. | `npx skills add tradermonty/claude-trading-skills@economic-calendar-fetcher -g -y` |
| 3 | `wshobson/agents@backtesting-frameworks` | 17K | Backtest framework selection/usage guidance (likely covers backtesting.py, backtrader, vectorbt). Supports our strict validation gate. | `npx skills add wshobson/agents@backtesting-frameworks -g -y` |
| 4 | `0xhubed/agent-trading-arena@risk-management` | 2K | Position sizing, stop placement, max DD, R-multiple accounting. FTMO-shaped risk gates. | `npx skills add 0xhubed/agent-trading-arena@risk-management -g -y` |
| 5 | `jeffallan/claude-skills@pandas-pro` | 5.8K | Pandas idioms for OHLCV wrangling, dedupe/resample, Parquet IO. | `npx skills add jeffallan/claude-skills@pandas-pro -g -y` |
| 6 | `claude-office-skills/skills@telegram-bot` | 6.2K | Build the Telegram alerter so bot pings on fill/stop/daily-stop/error. (Distinct from `telegram:*` host channel.) | `npx skills add claude-office-skills/skills@telegram-bot -g -y` |
| 7 | `tradermonty/claude-trading-skills@breakout-trade-planner` | 3.1K | Trade planning template — risk per trade, R-multiples, journaling. Secondary fit. | `npx skills add tradermonty/claude-trading-skills@breakout-trade-planner -g -y` |
| 8 | `404kidwiz/claude-supercode-skills@quant-analyst` | 1.1K | Statistical analysis of returns, Sharpe/PF/MC, equity curve stats. | `npx skills add 404kidwiz/claude-supercode-skills@quant-analyst -g -y` |
| 9 | `anthropics/skills@xlsx` | 189K | Export FTMO-compliant trade journal + daily reports to Excel. | `npx skills add anthropics/skills@xlsx -g -y` |
| 10 | `jakeschincariol/day-trader-skill@trader-timemachine` | 106 (`LOW`) | User asked for this repo. Replay/time-machine for backtest walk-through. Secondary — only if above do not cover. | `npx skills add jakeschincariol/day-trader-skill@trader-timemachine -g -y` |
| 11 | `jakeschincariol/day-trader-skill@trader-scanner` | 102 (`LOW`) | Scanner-style setup logic. Mostly US equities; limited forex fit. | `npx skills add jakeschincariol/day-trader-skill@trader-scanner -g -y` |
| 12 | `jakeschincariol/day-trader-skill@trader-entry` | 102 (`LOW`) | Entry logic. Low installs; equity-biased. | `npx skills add jakeschincariol/day-trader-skill@trader-entry -g -y` |
| 13 | `nawfdev/mq5_skills@mql5-ea-expert` | 44 (`LOW`) | MQL5 EA code. We are Python-first, skip unless we need an EA. | — |
| 14 | `acaprino/daodan@mt5-trading` | 9 (`LOW`) | MT5 Python examples, too low. Skip. | — |
| 15 | `felixwayne0318/aitrader@nautilustrader` | 31 (`LOW`) | Nautilus Trader. We chose MT5 package in Q6, skip. | — |

## Gaps — no skill meets threshold

| Gap | Decision |
|---|---|
| Dukascopy / tick-data downloader skill | Not needed — user supplied local CSV. |
| Windows service / Task Scheduler packaging | No skill ≥ 1K installs. Build directly with `nssm` or Task Scheduler + python entrypoint. |
| Walk-forward + Monte Carlo backtest skill specifically | No skill ≥ 1K installs for this. Implement with `wshobson/agents@backtesting-frameworks` guidance + `0xhubed/agent-trading-arena@risk-management`. |
| FTMO rule enforcement (daily loss, consistency, DD) | No dedicated skill. Code it from spec. |

## Top-5 install ranking (recommend to parent)

Ask user before installing. In priority order:

1. `wshobson/agents@backtesting-frameworks` — 17K installs. Backtest is the critical path; this is the highest-reputation skill in scope.
2. `tradermonty/claude-trading-skills@mt5-robot-tester` — 2.4K installs. MT5 execution-side guidance from a trading-skills author.
3. `tradermonty/claude-trading-skills@economic-calendar-fetcher` — 3.5K installs. Directly implements Q10 news blackout.
4. `0xhubed/agent-trading-arena@risk-management` — 2K installs. FTMO-shaped risk discipline for our 1% / 4% / 10% gates.
5. `jeffallan/claude-skills@pandas-pro` — 5.8K installs. We will do heavy pandas/Parquet work on 12 years of 1m data; this reduces footguns.

Optional add-ons after top 5: `claude-office-skills/skills@telegram-bot` (6.2K) for the alerter, `404kidwiz/claude-supercode-skills@quant-analyst` (1.1K) for stats discipline.
