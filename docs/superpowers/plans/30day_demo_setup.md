# 30-Day Demo Operator Runbook

Spec: `docs/superpowers/specs/2026-11-11-30day-demo-scaffolding.md`.
Strategy: RSI2-USATECHIDXUSD commit `1465ef3`.
Start date: 2026-11-11 (first poll succeeded).

## Daily — automate via Windows Task Scheduler

The poll must run once per weekday after the US cash close (16:00 NY) and before midnight UTC of the same day. Set the trigger for 23:00 Asia/Kolkata (which is 17:30 UTC, 12:30 NY — just after the close).

### Setup (one-time)

1. Press Win+R, type `taskschd.msc`, Enter.
2. Right-click **Task Scheduler Library** → **Create Task** (not "Create Basic Task" — we need the full dialog).
3. **General** tab:
   - Name: `RSI2 Demo Poll`
   - Description: `30-day RSI(2) NAS100 paper trading demo`
   - Check **Run whether user is logged on or not**
   - Check **Run with highest privileges** (needed so the MT5 terminal is reachable when your session is locked)
4. **Triggers** tab → **New**:
   - Begin the task: **On a schedule**
   - Settings: **Daily**, start `2026-11-12 23:00:00` local time, recur every 1 day
   - Advanced → **Repeat task every 1 day** → **for a duration of 30 days**
   - Enabled: checked
5. **Actions** tab → **New**:
   - Action: **Start a program**
   - Program/script: `C:\personal\v_17\.venv\Scripts\python.exe`
   - Add arguments: `C:\personal\v_17\scripts\demo_poll_mt5.py`
   - Start in: `C:\personal\v_17`
6. **Conditions** tab:
   - Uncheck **Start the task only if the computer is on AC power**
   - Uncheck **Stop if the computer switches to battery power**
7. **Settings** tab:
   - Check **If the task fails, restart every 10 minutes, attempt 3 times**
   - Allow task to be run on demand: checked
8. Click **OK**. Enter your Windows password when prompted.

### Verify

- Right-click the task → **Run**. Check that `out/demo/last_poll.txt` updates to today's timestamp.
- The MT5 terminal must be running and logged into `53143050` when the task fires. Set MT5 to auto-launch at Windows startup if your machine reboots.

## Weekly — manual review

Every Sunday evening run:

```
.venv\Scripts\python.exe scripts\demo_report.py
```

Check for abort conditions per spec section 6. If any flag appears, stop the task immediately and open an issue.

## At day 30 — manual sign-off

1. Run `scripts/demo_report.py` and save the output.
2. Open `out/demo/trade_log.jsonl` and visually scan every entry+exit row. Confirm:
   - No bar-boundary drift (entry_date on T+1, exit_date on signal day + 1-10 bars).
   - r_dist values consistent with ~1% of entry price.
   - pnl_r values finite and bounded (−5 to +5 R).
3. Open `out/demo/equity_curve.jsonl` and spot-check a few poll rows. Confirm RSI/SMA values look sane.
4. Only after manual sign-off: proceed to the FTMO Standard $10k challenge signup. No automation will initiate this step.

## Abort — if you need to stop the demo mid-run

```
schtasks /Change /TN "RSI2 Demo Poll" /Disable
```

No cleanup needed on the JSONL files — they are append-only logs, safe to leave.
