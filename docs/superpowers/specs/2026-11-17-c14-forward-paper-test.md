# RSI2 forward paper test (cycle 14 follow-up)

**Status:** FROZEN 2026-11-17. User "yes to all" on Q12-Q15. Committed before the forward test starts.

## What runs

- **Strategy:** original RSI2 exactly as in cycle 4B / cycle 14 candidate "original": RSI(2) < 10 on the daily close →
  buy next open; exit at the first close above SMA(5), else after 10 bars. Long only. No trend filter.
  Engine: `src/v17/live/rsi2_demo.py::process_bars` (demo ADR 001; TIME_CAP parity with the backtest).
- **Markets:** IC Markets MT5 demo `USTEC` (Nasdaq 100) and `US500` (S&P 500), using the **broker's own D1 bars**.
- **Paper only:** no orders are ever sent.
- **Costs:** fixed per fill, about the broker's spread: USTEC 1.0 point, US500 0.5 point (MT5 spread on
  2026-11-17: 0.9 and 0.3).
- **Schedule:** existing task `RSI2 Demo Poll` (daily 23:00 IST) and `RSI2 Demo Watchdog` (23:30 IST), re-enabled.
- **Logs:** `out/forward_c14/<SYMBOL>/` (`state.json`, `trade_log.jsonl`, `equity_curve.jsonl`), plus
  `out/forward_c14/last_poll.txt` for the watchdog.
- **Start:** clean state; the first poll processes only the latest closed bar (no backfill).

## Success rule (Q14), fixed now

Evaluated once **at least 30 closed forward trades** exist across both markets combined:
1. Average R per trade (after the fixed costs above) **> 0**, and
2. it is **above random buying** over the same forward period: the average R of a long trade entered at the open of
   a random day in the same period and exited with the same rule, computed over all eligible days from the broker's
   D1 history (mean of all such trades, per market, weighted by each market's forward trade count).

## Money rule (Q15)

No FTMO fee until the success rule is met.

## Old demo

The cycle 4B demo logs in `out/demo/` are kept unchanged as history; the old single-symbol poll is replaced.
