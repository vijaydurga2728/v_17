# Demo ADR 001 — RSI2 demo poll: catch-up, idempotency, TIME_CAP parity, clock reset

**Status:** ACCEPTED
**Date-authorized:** 2026-11-17 (user, grilling rounds 1-2: "yes to all")
**Supersedes-parts-of:** `2026-11-11-30day-demo-scaffolding.md` (poll mechanics, day-30 review date)
**Strategy rules:** unchanged. RSI2-USATECHIDXUSD as locked at commit `1465ef3`.

## Problem (found in 2026-11-17 project audit)

1. **Polls stopped after 2026-11-12 04:57 UTC.** Task `RSI2 Demo Poll` was registered with
   `LogonType=Password`, `StartWhenAvailable=False`, `StopIfGoingOnBatteries=True`, not the repo XML.
   Last result `0x800710E0` ("operator or administrator has refused the request"). 11-12, 11-13, 11-16 missed.
   The scaffolding gate "30 polls without session drop" is therefore failed.
2. **Missed polls lost signals.** The poll only evaluated the latest closed D1 bar.
3. **`bars_held` counted polls, not bars.** Five manual runs on 11-11 would have aged an open trade by 5.
4. **TIME_CAP off-by-one vs backtest.** `rsi2_runner` exits on TIME_CAP at the close of
   `entry_idx + TIME_CAP_D1`; the poll exited one bar earlier (`bars_held >= TIME_CAP_D1`).
5. **Stale MT5 history on attach.** First `copy_rates_from_pos` after attach returned bars only up to 11-11
   while the terminal was still syncing; the poll logged "no new bars" as success.

No trade was open at any point, so no recorded P&L is affected.

## Decision

- New pure engine `src/v17/live/rsi2_demo.py::process_bars`. It replays every closed D1 bar newer than
  `state.last_processed_ts` in order. Re-running on the same bars is a no-op. `bars_held` counts closed bars.
  Exit rule parity with `rsi2_runner`: TIME_CAP when `bars_held > TIME_CAP_D1`.
- `scripts/demo_poll_mt5.py` uses the engine, writes `state.json` atomically, logs one equity row per
  processed bar, and retries until the current D1 bar is < 4 days old; else exits 6 (`STALE history`).
- State migrated once: `last_processed_ts` set to the 2026-11-11 bar (backup `out/demo/state.pre_adr001.json`).
  Catch-up run 2026-11-17 14:39 UTC replayed 11-12, 11-13, 11-16: no entries (11-16 RSI(2)=10.66).
- Task re-registered from `scripts/rsi2_demo_poll_task.xml` (InteractiveToken, StartWhenAvailable,
  no battery stop) via `scripts/fix_demo_task.bat` (requires admin).
- New watchdog `scripts/demo_poll_watchdog.py`, task `RSI2 Demo Watchdog` daily 23:30 IST: alerts if
  `last_poll.txt` older than 20 h. Telegram if `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` are in `.env`;
  otherwise Windows `msg` popup.

## Clock reset

- **Day 1** = first successful *scheduled* poll under the new task registration.
- **Day-30 review** = Day 1 + 30 calendar days. Replaces 2026-12-11.
- Polls 2026-11-11 to 2026-11-17 are retained in the logs but do not count toward the 30.
- Gate unchanged: 30 days of scheduled polls with no missed weekday; any watchdog alert during the
  window is logged in the review.

## Verification

- `tests/unit/live/test_rsi2_demo.py`: incremental polls with random gaps and same-day repeats produce
  trades identical (entry ts, exit ts, reason, pnl_r) to `run_rsi2_oos_batch` on 3 seeds; TIME_CAP exit
  bar; repeat-poll no-op; first-run behaviour; legacy state migration. Reverting the cap check to the old
  `>=` fails 3 tests.
- `tests/unit/live/test_demo_poll_watchdog.py`: age computation.
- Full suite at time of change: 545 passed, 1 skipped, 1 xfailed.
