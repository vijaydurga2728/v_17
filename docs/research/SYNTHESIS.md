# Phase 1 Research — Synthesis & Exit

Date: 2026-10-28
Inputs: `last30days.md`, `agent-reach.md`, `find-skills.md`, `deep-research.md`.

## Stack Decision (locked)

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | MT5 pkg + ecosystem |
| ICT primitives | `smartmoneyconcepts` (MIT, joshyattridge) | Battle-tested FVG/OB/BOS/CHoCH/liquidity/sessions |
| Backtest engine | **Custom event-driven** (numpy+pandas) | Nautilus no MT5, backtrader unmaintained, backtesting.py bar-only, vectorbt wrong paradigm |
| Live execution | `MetaTrader5` pkg + **single-threaded `MT5Gateway` + command queue** | Package is NOT thread-safe (verified) |
| Data | Local Dukascopy CSVs (bid+ask 1m 2014–2026, EURUSD+GBPUSD) | Already on disk, bank-quote grade |
| Calendar | FF JSON feed (`nfs.faireconomy.media/ff_calendar_thisweek.json`) + archived GitHub dumps for historical | Free, reliable, matches FTMO |
| Storage | Parquet (tick/1m) + SQLite (trades, equity, state) | Fast + simple |
| Scheduler | APScheduler + Windows service wrapper (`nssm` or Task Scheduler) | London killzone cron |
| Alerting | Telegram bot | Fills, stops, daily-stop, errors |
| Testing | pytest + `FakeMT5` fixture | Unit + integration + backtest regression |
| Logging | structlog JSONL + rotating file | Audit trail required for FTMO |

**No ML/AI models.** Deterministic rules only. MVP.

## Validation Framework (hard-locked from research)

- **IS/OOS 60/40 split** on 2014–2026 Dukascopy data.
- **Walk-forward 12 anchored folds** (Pardo methodology).
- **Monte Carlo 1000 runs: 500 trade-order permutations + 500 block-bootstrap (block=5)** — preserves losing-streak clustering.
- **Pass gate** (all must hold on OOS):
  - PF ≥ 1.8
  - Sharpe ≥ 2.0
  - Max DD < 6%
  - Winrate ≥ 50%
  - MC 5th-pct PF ≥ 1.3
  - MC 95th-pct max DD ≤ 8% (FTMO 10% − 2% buffer)
  - ≥ 200 OOS trades
- **Hard block on live/demo order_send until gate pass.**

## FTMO Rule Enforcement (hard-locked)

- Daily loss 5% (soft stop 4% → auto-flat + lockout rest of day).
- Overall DD 10% (hard kill).
- Min trading days: 4 (Challenge).
- **Consistency rule 2026-10-12: best day ≤ 30% of total profit** — risk engine must throttle or skip entries if streak would breach this.
- News trading allowed on Challenge; we blackout ±5 min high-impact anyway (own choice).
- Weekend hold allowed on Challenge.
- EA/bot allowed; no HFT, no grid, no martingale, no copy-trading, no latency arb.
- Scaling plan: 25% size up at +10%, caps at $400k.

## Reusable Artifacts (port, don't reinvent)

1. `smartmoneyconcepts` → `pip install smartmoneyconcepts` — core detection lib.
2. `fallenpheonix23/ict-trading-bot/ict_structures.py` + `ict_backtest.py` → ATR-stop logic + param set (ATR_STOP_BUFFER=1.0, MIN_STOP_PCT=0.005, OB displacement ≥2.0×ATR, MSS swing=10 bars body>1.5×ATR, zone staleness=30, partial 1.5R → trail BE, ADX 18L/25S).
3. `sixscripts-ai/train-ict/.../silver_bullet.py` + `judas_swing.py` → reference shape only (unlicensed → re-implement).
4. `zakariab0/ozo` → MT5 session scheduler + order lifecycle patterns.
5. `SrsBlack/ict-knowledge-library` → canonical rule reference for Phase 2 spec.

## Candidate Skills (install only after user says yes)

1. `wshobson/agents@backtesting-frameworks` (17K)
2. `tradermonty/claude-trading-skills@mt5-robot-tester` (2.4K)
3. `tradermonty/claude-trading-skills@economic-calendar-fetcher` (3.5K)
4. `0xhubed/agent-trading-arena@risk-management` (2K)
5. `jeffallan/claude-skills@pandas-pro` (5.8K)

## Risks (ranked)

1. **No public ICT bot has honest forward-tested equity curve.** Edge may not exist after costs. Mitigation: strict gate; if fail, iterate setup rules or kill project — no curve fitting.
2. **`MetaTrader5` package not thread-safe.** Mitigation: single-thread `MT5Gateway` + queue + reconnect logic; `FakeMT5` for all tests.
3. **FTMO rules can change mid-project** (seen in 2026). Mitigation: rule constants file + weekly manual ToS check + rebacktest.
4. **Consistency rule 30%** can be breached by one hot day. Mitigation: equity-aware position sizer that scales down after a big day.
5. **ICT concepts are ambiguous** (FVG mitigation, OB validity, MSS confirmation have multiple definitions). Mitigation: pick ONE formal definition per concept in SPEC, cite source, do not mix.
6. **Data gaps / timezone bugs** (DST, broker-vs-UTC, bid-vs-ask separation). Mitigation: data ingestion pipeline with assertions; UTC canonical, convert for killzone display only.
7. **Overfit to EURUSD+GBPUSD London killzone.** Mitigation: regime filter test (trending vs ranging years) in backtest; honest about scope.
8. **Reddit sentiment blind spot** (403 in last30days scan). Low priority; manual check later.
9. **Prop-firm withdrawal risk** (unrelated to code). Mitigation: diversify prop firms post-first-payout; not in MVP scope.

## Exit Criteria Phase 1 (met)

- [x] Stack picked.
- [x] Risks listed.
- [x] Reusable artifacts identified.
- [x] Validation framework formalized.
- [x] FTMO rules enumerated.

**Ready for Phase 2: Spec.**
