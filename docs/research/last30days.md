# last30days Research — ICT/SMC Intraday Bot for FTMO (EURUSD/GBPUSD London Killzone)

**Window**: 2026-08-29 → 2026-10-28 (3 queries, 60–90d lookback for sparser topics)
**Engine**: last30days v3.31.0 keyless, no Brave/Serper key, no ScrapeCreators key, no X token
**Reddit auth-failed every query (HTTP 403)** — no Reddit community voice captured. Polymarket timed out. Treat community sentiment data as thin; web/GitHub are the primary signal.

---

## Executive summary (5 bullets)

1. **MetaTrader5 Python package is NOT thread-safe** — confirmed by third-party dev writing a real MT5 gateway (`mohmdstag7-cmd/Tr` PR #11, 2026-09-27). Any live runner must own all MT5 calls through a single-threaded command queue (`MT5Gateway`), with a `FakeMT5` simulator for CI. Non-negotiable architectural constraint — if we ignore it we will hit random crashes under concurrent 1m-tick polling + order sends.
2. **FTMO Challenge via ICT is a crowded content niche but almost no honest forward-tested bots exist in the open**. Vendor blog posts (ictflow.com, backtrex.com, propfundhub.com, propfirmpickr.com) describe the strategy with no equity curves, no OOS stats, no slippage audits. The validated recipe they all converge on: 1–2 high-quality trades/day, tight sub-1% risk, FVG+OB+MSS confluence, London/NY killzones. This matches our plan, which is good — but it's also what every content farm sells, so community proof is weak.
3. **Prop firm rules are shifting faster in 2026 than any prior year**. PropFirmPickr (`propfirmpickr.com/blogs/prop-firm-rules-2026-whats-changed`) reports: *consistency rules dropped at many firms, drawdown models tightened, news-trading restrictions relaxed*. PropFundHub (`propfundhub.com/blog/prop-firm-rule-changes-updates-2026-what-every-trader-must-know-now`) warns tighter consistency triggers are "catching traders off guard" and payout denials are rising. **Implication**: hard-code the current FTMO Challenge $100k rules as config, re-verify ToS before every submission, and keep a "worst-case" rule set as the backtest filter (strictest daily DD + consistency + news blackout) so a mid-challenge rule tweak doesn't disqualify us.
4. **MT5 Python architecture pattern (field-validated)**: run MT5 terminal on the same Windows machine, use IPC via the `MetaTrader5` package, push data to a backend over WebSocket/REST (`igarukas4/trading-engine-dev` #2, `azumag/docich` #579). Linux requires Wine (fragile). Must handle reconnect and symbol-visibility toggles. Order-send-blocking-the-polling-thread is the top reported crash cause — reinforces the single-gateway-queue decision.
5. **No publicly visible ICT bot repo (GitHub) with honest live-trading P&L surfaced in this window**. Our shortlisted repos (`joshyattridge/smart-money-concepts`, `OPKYEI/ICT-Trading`, `futureteck/ICT_Automated_Trading_System`, `zakariab0/ozo`, `fallenpheonix23/ict-trading-bot`, `dextergsm/ict-trading`) are indicator/signal libraries, not audited systems. Use them as reference implementations for FVG/OB/MSS detectors (saves weeks), **never as a strategy to copy**. The strategy must be built, backtested, and audited by us.

---

## Detailed findings by scope item

### 1. FTMO Challenge pass/fail stats and common failure causes
Vendor sources only (no FTMO-published failure cohort stats surfaced this window). Reported top failure causes across content farms (consistent across ictflow.com, backtrex.com, propfundhub.com): over-sizing on recovery, breaching daily DD by holding losers through NY session, breaching consistency rule by one outsized winning day, revenge trading after news spikes. **Design implication**: already handled by 1% fixed risk + 4% hard daily lockout + killzone-only session + news blackout.

### 2. ICT/SMC algo bot results — honest vs hype
No honest forward-tested public results captured this window. All vendor material pattern-matches the same recipe without posting trade blotters. Treat anyone claiming >60% winrate on ICT discretionary scalping as marketing until shown Myfxbook-verified or FTMO-verified equity. This is why our strict validation gate (PF≥1.8, Sharpe≥2.0, winrate≥50%, MC 95% CI PF>1.3, 200+ OOS trades) exists.

### 3. London killzone / Silver Bullet / Judas Swing — current status
Vendor consensus still endorses the model (ictflow.com, Scribd `ICT-PropFirm-Strategy-SimpleGuide`). No evidence of degradation in H2 2026. Zero community pushback captured — but Reddit was blocked, so we have blind spot. Keep walk-forward 12 folds to catch regime decay empirically rather than relying on sentiment.

### 4. MetaTrader5 Python package pain points
- **Not thread-safe** — `mohmdstag7-cmd/Tr` PR #11 (https://github.com/mohmdstag7-cmd/Tr/pull/11). Must wrap in single-threaded owner with a command queue.
- **Windows-only in practice** — Linux via Wine is unreliable; `igarukas4/trading-engine-dev` #2 (https://github.com/igarukas4/trading-engine-dev/issues/2).
- **Symbol must be visible in Market Watch before `copy_rates_from` returns data** — common silent-fail cause. Call `symbol_select(symbol, True)` first.
- **Reconnect + session-expiry handling is on us** — package does not auto-reconnect gracefully.
- **The Python Quants** (YouTube, 4,186 views) covers the pip-install path and basic order send — reasonable baseline tutorial.
- Blog: `lucca.team/blog/mt5-automation-python.html` — concrete code examples.
- Comparable alt-stack: `azumag/docich` #579 (https://github.com/azumag/docich/issues/579) switched *to* MT5 Python from OANDA REST because OANDA's PAT path is too heavy for pricing-only use. Validates our choice.

### 5. News trading restrictions FTMO 2026
No FTMO-specific restriction change captured. Industry-wide trend (propfirmpickr.com, propfundhub.com): news restrictions **relaxed** at many firms in 2026, but consistency and drawdown rules tightened. **We still implement full ±5 min high-impact blackout** — if the edge needs news to be profitable, the edge is noise.

### 6. Prop firm scams / rule changes
No major FTMO scandal in-window. PropFundHub (`propfundhub.com/blog/prop-firm-rule-changes-updates-2026-what-every-trader-must-know-now`): "prop firms are implementing rule changes faster than at any point in industry history ... new restrictions on news trading are forcing strategy overhauls ... evolving drawdown calculations are triggering unexpected account breaches." PropFirmMap (`propfirmmap.com`) tracks 128+ firms; use their comparison page as a monthly spot-check before paying for a new challenge seat.

### 7. ICT bot repos with honest forward-tested results
**None found with verified live P&L** in the window. Shortlist repos remain useful as component sources only:
- `joshyattridge/smart-money-concepts` — pandas FVG/OB/MSS detectors. Best cite for indicator reuse.
- `OPKYEI/ICT-Trading`, `futureteck/ICT_Automated_Trading_System`, `dextergsm/ict-trading`, `fallenpheonix23/ict-trading-bot`, `zakariab0/ozo`, `islero/ICT-NT`, `sixscripts-ai/train-ict`, `SrsBlack/ict-knowledge-library` — read, extract detectors, do not trust strategy wiring.

---

## Risks surfaced by research

- **R1**: FTMO rule drift mid-challenge. Mitigation: re-fetch ToS before every submission; keep a `rules.yaml` with worst-case values as the backtest gate.
- **R2**: `MetaTrader5` thread-safety → random live crashes. Mitigation: single-threaded `MT5Gateway` + command queue + `FakeMT5` for CI (pattern already validated by third party).
- **R3**: No independent proof the setup still works in 2026 regime. Mitigation: strict walk-forward 12 folds + Monte Carlo + 2026 held-out year as final OOS.
- **R4**: Reddit community data missing this run — unknown unknowns. Mitigation: next pass with Reddit auth working, or run `agent-reach` fork to pull Reddit subs directly (`r/FTMO`, `r/algotrading`, `r/Forex`).
- **R5**: Vendor echo chamber risk — all public ICT content converges on the same recipe. Could mean "it works" or "everyone copies the same guru." Mitigation: statistical gate decides, not consensus.

---

## File written
`C:/personal/v_17/docs/research/last30days.md`
