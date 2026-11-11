# 30-Day Demo Scaffolding Spec (FROZEN)

**Status:** FROZEN 2026-11-11.
**Branch:** `ensemble-h1-cycle4`.
**Strategy under test:** RSI2-USATECHIDXUSD (commit `1465ef3`).
**Broker:** IC Markets Demo — server `ICMarketsSC-Demo`, account `53143050`, currency USD, starting balance $10,000.
**Symbol:** `USTEC` (verified same underlying as Dukascopy `USATECHIDXUSD`).

## 1. PRE-REG DEVIATION (read first)

The `user_trading_goals.md` memory file commits to a **90-day demo** before any paid FTMO challenge. This spec cuts it to **30 days**. Reasons given by user: wants to shorten calendar time to first attempt. Reasons against the cut: 30 trading days ≈ 22 D1 bars; RSI(2) fires on ~15% of days, so expected sample = 3-5 live trades over the demo window. That is statistically meaningless on its own.

Compensating mitigation: use the demo as a **plumbing test only**, not a performance test. The demo confirms:

1. Credentials and connectivity hold for 30 days without session drops.
2. Live broker D1 bars match Dukascopy dev-cache schema (open/high/low/close fields, no NaN, no bar-boundary drift).
3. RSI(2) signal fires on the same days in live data as a replay of the same window in dev infra.
4. Paper-trade log shape and schema work for post-mortem analysis.

The demo does NOT produce a statistically valid live-PF estimate; 3-5 trades cannot. Any decision to go to paid FTMO after this 30-day run inherits the full cycle-4B statistical uncertainty — the demo cannot upgrade it.

**Live money still gated on:** (a) this plumbing test passing, (b) manual review by user of each paper trade for correctness, (c) user signing the full p-hack ledger.

## 2. Daily operation

A Windows Task Scheduler entry (manual setup — see `docs/superpowers/plans/30day_demo_setup.md` after first run) triggers `scripts/demo_poll_mt5.py` once per weekday at 23:00 Asia/Kolkata (17:30 UTC = 12:30 NY = well after the US cash close at 16:00 NY). This ensures the latest D1 bar is final before the poll reads it.

The poll script performs, in order:

1. Load `.env` with `override=True`. Initialize MT5.
2. Fetch last 400 D1 USTEC bars from MT5 (enough for 252-day lookback, though RSI(2) only needs 10).
3. Read `out/demo/state.json` for any open paper trade.
4. If a paper trade is open: check exit conditions on the latest CLOSED bar. If exit triggers, append row to `out/demo/trade_log.jsonl` and clear open trade from state.
5. If no paper trade open AND RSI(2) < 10 on the latest closed bar: open a new paper trade. Entry price = next bar's open + slippage 1.0. Record entry in state and append to `trade_log.jsonl`.
6. Append a daily row to `out/demo/equity_curve.jsonl`: date, cumulative pnl_r, open_trade state, last_price.
7. Shutdown MT5.

No real MT5 orders are sent. Everything is paper, written to local JSONL.

## 3. File layout

- `out/demo/state.json` — current open trade (or empty).
- `out/demo/trade_log.jsonl` — one line per entry and per exit, with full price + timestamp.
- `out/demo/equity_curve.jsonl` — one line per poll call, regardless of trade activity.
- `out/demo/last_poll.txt` — ISO timestamp of last successful poll.

## 4. Review cadence

User runs `scripts/demo_report.py` once per calendar week (Sundays). Report prints: days elapsed, trades opened, trades closed, cumulative pnl_r, PF, WR, avg_r, max_dd_r, live-vs-dev discrepancy flags.

At day 30 (or at 5 completed trades, whichever comes first): user reviews the full `trade_log.jsonl` manually. If no bar-boundary drift, no schema mismatches, no stuck opens, the plumbing test passes. If the live trade pnl_r mean is grossly different (>2× or <0.5×) from the dev baseline of 0.74, flag for investigation before any FTMO attempt.

## 5. Explicit non-goals

- No live-order execution.
- No automated FTMO attempt trigger.
- No performance-based verdict — too few trades for statistics.
- No re-tuning of RSI(2) parameters during the demo window.

## 6. Abort conditions

Immediately stop the demo and alert the user if any of these occur:

- MT5 connection fails more than 3 days in a row.
- A paper trade stays open longer than TIME_CAP_D1 + 2 bars (indicates exit logic bug).
- Live USTEC D1 bar's close price differs from any other data source (manual check) by more than 0.5% without a corporate action.
- Account `53143050` shows an actual open position (indicates accidental live execution — should never happen since we only read).
