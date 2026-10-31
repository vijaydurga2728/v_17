# v17 Profitability Validation Rules

Every rule below must PASS before any claim of "profitable system" or any live FTMO deployment. Each rule is binary: pass or fail. "Mostly passes" means fails.

---

## A. Code integrity (zero tolerance for bugs that inflate returns)

**R1. No lookahead in signal generation.** Every `at`, `created_at`, `mitigated_at`, `price`, `close` used by any gate at time `now` must be derivable from bars where `ts <= now`. No field computed from a future bar may filter a past gate. Verified by audit script that mirrors every gate with explicit `<= now` comparison.

**R2. No lookahead in fill simulation.** `entry_fill` uses next bar open. `exit_fill_on_bar` uses current bar OHLC. SL-vs-TP tie-break on same bar: pessimistic (SL wins). No bar's close is used before the bar closed.

**R3. Live/backtest parity.** Every gate, filter, cost, risk check, and config constant in `src/v17/backtest/` must have an exact equivalent in `src/v17/live/`. Symmetric list — if `backtest.loop.EventLoop` calls `is_blackout`, `live.runner.LiveRunner` must call `is_blackout` with same window. Verified by paired integration test.

**R4. Dedupe guards present.** `(setup, side, trading_date)` dedupe applied in EventLoop. One trade per (setup, side) per day max.

**R5. Fill guards present.** Three guards after `entry_fill`:
- entry on correct side of SL
- entry slip from signal.entry ≤ 5 pips
- post-fill R:R ≥ `min_rr` (recomputed, not inherited from signal)

**R6. Mitigation lookahead-safe.** `Zone.mitigated_at` is a future-tagged field (set at precompute from future bars). Every reader checks `z.mitigated_at is not None AND z.mitigated_at <= now` — never just `is not None`.

**R7. No peeled gates in main.** Canonical ICT gates (bias, zone, sweep, MSS, RR, pip_SL) all present. "Peel for diagnostic" branches must be behind a config flag defaulting to canonical, never silently merged.

**R8. No test weakening.** No test may be modified to pass by lowering an assertion threshold. If a test fails, fix code or update the threshold EVIDENCE (not just the number). Record reason in the commit/task.

---

## B. Statistical sample (edge detection, not luck)

**R9. OOS trade count ≥ 200.** Walkforward out-of-sample trades aggregated across all folds must be ≥ 200. Below that, PF is noise.

**R10. Per-fold trade count ≥ 30.** No fold with fewer than 30 OOS trades is counted toward `folds_passed`. Thin folds cannot pass.

**R11. Minimum walkforward folds = 12.** 4+ years of data split into 12 anchored or rolling folds. 1 fold per quarter minimum.

**R12. Passed-fold ratio ≥ 0.6.** At least 60% of folds (`≥ 8/12`) must independently clear every PF/DD threshold in B.

**R13. Monte Carlo hybrid, 1000 runs.** Permutation + bootstrap of trade order. p5_pf > 1.0, p95_max_dd_pct ≤ 8%. Both.

**R14. Sharpe ≥ 1.0 on aggregated OOS.** 2.0 preferred. Below 1.0 is not an edge; it's variance.

**R15. Winrate not weaponized.** If PF ≥ threshold is achieved with winrate < 30%, strategy is tail-dependent. Reject unless Sharpe ≥ 1.5 AND no single trade accounts for > 20% of total P&L.

---

## C. Cost realism (backtest ≠ live if costs are wrong)

**R16. Spread calibrated to broker.** `COST_MODEL.spread_pips` matches the specific broker/account type. FTMO Normal: 0.6-0.9 pip EURUSD, 1.0-1.5 pip GBPUSD. FTMO Raw: 0.1-0.3 pip + commission. Must match the account you will deploy to.

**R17. Slippage ≥ 0.3 pip per side.** Zero slippage = fiction. Minimum 0.3 pip entry + 0.3 pip exit, more if the pair is less liquid.

**R18. Commission applied if non-zero.** Normal = 0. Raw = $3-7 per lot per side. Hard-coded 0 only if Normal.

**R19. Spread stress test passes.** Re-run full M6 gate with spread inflated 50% AND 100%. Both must still pass. If strategy fails at 50% inflation, do not deploy.

**R20. No fills better than market reach.** `exit_fill_on_bar` must not fill at a price the bar never touched. SL fill = `max(open, sl)` for SELL (not `min`).

---

## D. Risk engine (survives drawdown clusters)

**R21. Per-trade risk fixed and enforced.** `per_trade_pct` is a config value (not derived from signal). Live and backtest use same value.

**R22. Max concurrent positions enforced.** Risk engine blocks N+1 trade. Verified by regression test opening 4 trades with max=3 → 4th rejected.

**R23. Max trades per day enforced.** Daily counter resets at day change. Blocks N+1 trade with code `max_trades_today`.

**R24. Daily loss lockout.** Trades blocked for remainder of day after `|daily_realized_pnl| ≥ soft_daily_stop_pct * starting_equity`. Resets at day change.

**R25. Overall DD guard.** New entries blocked if drawdown from peak equity ≥ `max_overall_dd_pct`. Not reset.

**R26. Kill switch respected.** If `account.kill_active = True` or `KILL` sentinel file present, no new entries. Open positions managed to SL/TP only.

**R27. Position sizing never leaks.** `compute_lots(equity, per_trade_pct, stop_distance_pips, pip_value_per_lot, min_lot, lot_step)` uses zone-anchored stop distance (`sig.entry - sig.sl`), but the final trade's loss is computed from fill_entry. Risk sized to signal must match realized risk within tolerance. Regression test: fill-entry vs sig.entry delta × lots × pip value ≤ 10% of configured risk.

---

## E. News and session integrity

**R28. News filter wired in BOTH paths.** `is_blackout(symbol, now, window_min)` called in both `EventLoop.run` and `LiveRunner._tick_step`. Window = 2 min (FTMO rule). Both high-impact AND symbol-currency match.

**R29. News archive covers the test range.** `data/calendar/` has JSON files covering every month in the backtest range. No empty months.

**R30. Weekend/holiday bars excluded or ignored.** Backtest must not fire signals on Sunday session reopen (22:00-00:00 UTC Sun) or Christmas week (Dec 24-26) or similar low-liquidity windows.

**R31. Killzone windows match ICT doctrine.** Silver Bullet: three NY-time windows (03-04, 10-11, 14-15). Judas: 07:00-08:30 London. Window change requires a commit with ICT-doctrine citation (not "it works better").

---

## F. FTMO specific (challenge rules verbatim)

**R32. FTMO rules hardcoded match current contract.** `FTMO_CHALLENGE_10K` fields must match the exact challenge terms from ftmo.com for the plan tier user purchased. Verified against user-provided screenshot or contract text at deployment.

**R33. Consistency rule honored.** `consistency_best_day_pct_of_profit` enforced in `risk/consistency.py`. Trades rejected if `est_win` would push `best_day_pnl / total_realized_pnl > cap`.

**R34. Min trading days ≥ 4.** Backtest must show ≥ 4 distinct trading days with at least one trade each per walkforward fold.

**R35. Challenge timeframe reachable.** Expected days-to-10%-profit at observed daily P&L distribution ≤ FTMO challenge window (30-180 days depending on plan). If median days-to-target > plan window, strategy cannot pass in time regardless of overall edge.

---

## G. Honesty and reporting

**R36. Every metric has a committed run_id.** PF, DD, Sharpe, winrate claims must cite the run directory and the metrics.json path. No in-chat computed numbers without a run_id.

**R37. Zero-trade and single-trade results are NOT edge evidence.** `trades = 0` is a signal-firing failure. `trades = 1` with `pf = inf` is luck. Both must be reported as `insufficient_sample`, not as "profitable".

**R38. Previous bug fixes don't retroactively validate.** If a bug was found and fixed, all prior metrics are void. Re-run from scratch. Never aggregate pre-fix and post-fix numbers.

**R39. Spread/cost assumptions published with every result.** No PF claim without stating spread_pips, slippage_pips, commission_per_lot used.

**R40. "Profitable" has a precise definition.** A system is "profitable" ONLY if:
- R1–R39 all pass
- OOS PF ≥ 1.8
- OOS Sharpe ≥ 1.5 (2.0 preferred)
- OOS max_dd_pct < FTMO max_overall_dd_pct × 0.6 (safety buffer)
- MC p5_pf > 1.0
- Spread-stress at 100% still shows OOS PF ≥ 1.3

Any failing rule = NOT profitable. "Nearly profitable" = NOT profitable.

---

## H. Pre-live deployment gate (last 7 rules)

**R41. Paper-forward 2 months on same account type.** Deploy to FTMO Trial/Demo. Observe at least 60 calendar days. Live vs backtest divergence > 20% on PF or > 30% on DD = STOP, re-audit live/backtest parity.

**R42. GATE_PASSED sentinel is auto-written only.** `v17 validate` writes it. No human may create the sentinel manually. Live code refuses to start without it.

**R43. Reproducibility.** Any backtest run must reproduce bit-for-bit from `--seed`. Verified by double-run comparison.

**R44. Observability on from day 1.** Live runner must emit JSONL structured logs per trade (open, close, risk decision, blackout trigger). Daily report generated nightly. Telegram alerts for every entry, exit, and kill event.

**R45. Dry-run live for 1 full week.** `v17 live --dry-run` connects to real MT5, computes signals, logs trades, but places no orders. Review log for divergence from last backtest. ≥ 95% match on signal timestamps.

**R46. Rollback plan documented.** Kill switch tested. Account close procedure documented. Max loss before manual intervention defined.

**R47. No change under live.** Once `GATE_PASSED` written and live started, no code change to setups, risk engine, or cost model until the challenge resolves. Only kill switch allowed.

---

## I. Fail paths (what "not profitable" looks like, mandated end states)

**R48. Signal starvation.** OOS trades < 100. Report: `insufficient_signal_frequency`. Do not deploy.

**R49. Negative expectancy.** OOS PF < 1.0. Report: `no_edge`. Do not deploy.

**R50. Marginal edge, high DD.** OOS PF 1.0-1.3 and DD > 6%. Report: `edge_too_thin_for_dd_cap`. Do not deploy.

**R51. Edge in-sample only.** IS PF > 1.5 but OOS PF < 1.2. Report: `overfit`. Do not deploy.

**R52. Edge fails cost stress.** Passes at 0% spread inflation, fails at 50%. Report: `cost_fragile`. Do not deploy.

Any R48-R52 → the honest result is: v17 as currently coded does not qualify. Either replace setup family (new `SetupEngine` subclass with published edge) or shelve the live goal. Lowering any threshold in sections B-G to make a Fail Path "pass" is forbidden under R8.

---

## J. The "fully profitable" definition

A v17 configuration is **fully profitable** if and only if:

1. All 52 rules above (R1-R52 exclusions reversed) pass.
2. Full M6 gate passes.
3. Spread stress 50% and 100% both pass M6.
4. Paper-forward 60-day live-vs-backtest divergence < 20% PF, < 30% DD.
5. Reproducible from seed.
6. Every claim backed by a committed run_id and metrics.json.

Anything less: **not profitable.**

No "nearly". No "mostly". No "with tweaks". Binary.
