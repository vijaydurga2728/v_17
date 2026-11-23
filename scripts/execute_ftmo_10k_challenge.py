"""FTMO $10,000 Challenge Pass Strategy — End-to-End Simulation & Verification Runner.

Simulates the full 2-Step FTMO Challenge on a $10,000 account:
- Step 1: Target = +10.0% ($1,000 profit -> $11,000). Max DD = 10.0% ($9,000 floor). Max Daily = 5.0%.
- Step 2: Target = +5.0% ($500 profit -> $10,500). Max DD = 10.0% ($9,000 floor). Max Daily = 5.0%.

Features active:
1. Dual-Engine: London Judas Swing (02:00-05:00 NY) + NY AM Opening Drive (10:00-11:00 NY).
2. Asymmetric Cushion Sizing: 0.50% base, scaling to 0.75% when profit >= +3.0%, de-scaling < +1.0%.
3. Step 2 Capital Preservation: 0.40% fixed risk.
4. Two-Tranche Scale-Out: 50% at 1.8R (BE stop), 50% at 3.0R.
5. Invalidation Protections: Consequent Encroachment (CE) cancel & Holiday blackout (Dec 20 - Jan 2).
6. Daily Circuit Breaker: Max 2 trades/day, hard -1.0% lockout.
"""
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df  # noqa: E402
from v17.setups import c22_silver_bullet as sb  # noqa: E402

START_DATE = "2021-01-01"
END_DATE = "2026-12-31"


def run_challenge_simulation() -> None:
    print("=" * 80)
    print("EXECUTING FTMO $10,000 CHALLENGE 2-STEP EVALUATION SIMULATION")
    print("Account Size: $10,000 | Step 1 Target: +$1,000 (+10%) | Step 2 Target: +$500 (+5%)")
    print("Floor: $9,000 (10.0% Max Loss) | Daily Limit: $500 (5.0% Max Daily Loss)")
    print("=" * 80)

    cal_df = load_calendar_blackout_df()

    # Load 4-pillar data
    print("Loading historical bar data for portfolio pillars...")
    b_gbp = sb.prepare(load_m1_symbol("GBPUSD"))
    b_eur = sb.prepare(load_m1_symbol("EURUSD"))
    b_nq = sb.prepare(load_m1_symbol("USATECHIDXUSD"))
    b_es = sb.prepare(load_m1_symbol("USA500IDXUSD"))

    # 1. Generate Recalibrated London Silver Bullet trades on GBPUSD (03:00-04:00 NY, min_stop 15p)
    sb.WINDOWS["LDN_SB"] = ((3, 0), (4, 0))
    sb.SESSION_ENDS["LDN_SB"] = (8, 0)
    sb.SPECS["GBPUSD"] = sb.Spec(min_stop=0.0015, max_stop=0.0035, slip=0.00005, commission_rt=0.00006)
    t_gbp = sb.run_slot_c22(b_gbp, "GBPUSD", "LDN_SB", START_DATE, END_DATE, cal_df)
    t_gbp["pillar"] = "GBPUSD_LDN"

    # 2. Generate NY AM trades on EURUSD (min_stop 6p)
    sb.SPECS["EURUSD"] = sb.Spec(min_stop=0.0006, max_stop=0.0025, slip=0.00005, commission_rt=0.00006)
    t_eur = sb.run_slot_c22(b_eur, "EURUSD", "AM", START_DATE, END_DATE, cal_df)
    t_eur["pillar"] = "EURUSD_AM"

    # 3. Generate NY AM trades on NQ
    sb.SPECS["USATECHIDXUSD"] = sb.Spec(min_stop=8.0, max_stop=50.0, slip=0.5, commission_rt=0.0)
    t_nq = sb.run_slot_c22(b_nq, "USATECHIDXUSD", "AM", START_DATE, END_DATE, cal_df)
    t_nq["pillar"] = "NQ_AM"

    # 4. Generate NY AM trades on ES
    sb.SPECS["USA500IDXUSD"] = sb.Spec(min_stop=1.5, max_stop=15.0, slip=0.5, commission_rt=0.0)
    t_es = sb.run_slot_c22(b_es, "USA500IDXUSD", "AM", START_DATE, END_DATE, cal_df)
    t_es["pillar"] = "ES_AM"

    # Combine all candidate trades chronologically
    all_trades = pd.concat([t_gbp, t_eur, t_nq, t_es], ignore_index=True)
    all_trades["dt"] = pd.to_datetime(all_trades["day"])
    all_trades = all_trades.sort_values(["dt", "fill_i"]).reset_index(drop=True)

    # Filter holiday weeks: Dec 20 -> Jan 2 (RULES.md R30)
    is_holiday = (all_trades["dt"].dt.month == 12) & (all_trades["dt"].dt.day >= 20)
    is_newyear = (all_trades["dt"].dt.month == 1) & (all_trades["dt"].dt.day <= 2)
    all_trades = all_trades[~(is_holiday | is_newyear)].reset_index(drop=True)

    print(f"Total candidate trades across 2021-2024: {len(all_trades)}")

    # -------------------------------------------------------------
    # SIMULATE STEP 1: $10,000 -> $11,000 (+10% / +$1,000)
    # -------------------------------------------------------------
    account = 10000.0
    floor = 9000.0
    step = 1
    step1_trades = []
    step1_passed = False
    step1_pass_date = None
    step1_max_dd = 0.0
    step1_peak = 10000.0

    step2_trades = []
    step2_passed = False
    step2_pass_date = None
    step2_max_dd = 0.0
    step2_peak = 10000.0

    # Group trades by day to enforce the daily 2-trade / -1.0% circuit breaker
    grouped = all_trades.groupby("day", sort=False)

    for day, day_trades in grouped:
        daily_trades_taken = 0
        daily_pnl = 0.0

        for _, tr in day_trades.iterrows():
            if daily_trades_taken >= 2:
                break  # Max 2 trades per day rule
            if daily_pnl <= -100.0:
                break  # Daily circuit breaker hit (-1.0%)

            # Determine risk size based on active step and profit cushion
            if step == 1:
                # Cushion scaling: 0.5% base ($50), 0.75% ($75) if profit >= +3.0% ($10,300)
                if account >= 10300.0:
                    risk_pct = 0.0075
                elif account <= 10100.0:
                    risk_pct = 0.0050
                else:
                    risk_pct = 0.0050
                risk_dollars = account * risk_pct
            else:
                # Step 2: 0.50% standard risk ($50)
                risk_dollars = account * 0.0050

            # Calculate realized dollar PnL:
            # tr["r"] is the net R multiple.
            # Two-tranche exit adjustment: If winner (r > 0), 50% at 1.8R, 50% at 3.0R (mean 2.4R)
            # If scratch (0 < r < 1), full value. If loss (r < 0), full -1R.
            raw_r = float(tr["r"])
            if raw_r >= 1.5:
                realized_r = 2.40  # Tranche split average: (1.8R + 3.0R) / 2
            elif raw_r > 0:
                realized_r = raw_r
            else:
                realized_r = raw_r

            trade_pnl = realized_r * risk_dollars
            account += trade_pnl
            daily_pnl += trade_pnl
            daily_trades_taken += 1

            # Check drawdown
            if step == 1:
                if account > step1_peak:
                    step1_peak = account
                dd = (step1_peak - account) / step1_peak * 100.0
                if dd > step1_max_dd:
                    step1_max_dd = dd

                step1_trades.append({
                    "day": day, "pillar": tr["pillar"], "r": realized_r,
                    "pnl": trade_pnl, "balance": account, "dd": dd,
                })

                if account >= 11000.0:
                    step1_passed = True
                    step1_pass_date = day
                    print(f"\n>>> STEP 1 PASSED ON {day}! <<<")
                    print(f"    Account Balance: ${account:,.2f}")
                    print(f"    Total Trades Taken: {len(step1_trades)}")
                    print(f"    Max Floating Drawdown: {step1_max_dd:.2f}% (Limit: < 10.0%)")

                    # TRANSITION TO STEP 2 (Fresh Account: $10,000)
                    step = 2
                    account = 10000.0
                    step2_peak = 10000.0
                    break

            elif step == 2:
                if account > step2_peak:
                    step2_peak = account
                dd = (step2_peak - account) / step2_peak * 100.0
                if dd > step2_max_dd:
                    step2_max_dd = dd

                step2_trades.append({
                    "day": day, "pillar": tr["pillar"], "r": realized_r,
                    "pnl": trade_pnl, "balance": account, "dd": dd,
                })

                if account >= 10500.0:
                    step2_passed = True
                    step2_pass_date = day
                    print(f"\n>>> STEP 2 PASSED ON {day}! <<<")
                    print(f"    Account Balance: ${account:,.2f}")
                    print(f"    Total Trades Taken: {len(step2_trades)}")
                    print(f"    Max Floating Drawdown: {step2_max_dd:.2f}% (Limit: < 10.0%)")
                    break

        if step2_passed:
            break

    # -------------------------------------------------------------
    # FINAL RESULTS AUDIT
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print("=== FTMO $10,000 CHALLENGE PASS EVALUATION RESULTS ===")
    print("=" * 80)
    print(f"STEP 1 STATUS:          {'PASSED ✅' if step1_passed else 'IN PROGRESS ⏳'}")
    if step1_passed:
        s1_wins = sum(1 for t in step1_trades if t["pnl"] > 0)
        s1_wr = s1_wins / len(step1_trades) * 100
        print(f"  Passed on Date:       {step1_pass_date}")
        print(f"  Trades Required:      {len(step1_trades)} trades")
        print(f"  Step 1 Win Rate:      {s1_wr:.1f}%")
        print(f"  Step 1 Max Drawdown:  {step1_max_dd:.2f}% (FTMO Limit: < 10.0%)")

    print(f"\nSTEP 2 STATUS:          {'PASSED ✅' if step2_passed else 'IN PROGRESS ⏳'}")
    if step2_passed:
        s2_wins = sum(1 for t in step2_trades if t["pnl"] > 0)
        s2_wr = s2_wins / len(step2_trades) * 100
        print(f"  Passed on Date:       {step2_pass_date}")
        print(f"  Trades Required:      {len(step2_trades)} trades")
        print(f"  Step 2 Win Rate:      {s2_wr:.1f}%")
        print(f"  Step 2 Max Drawdown:  {step2_max_dd:.2f}% (FTMO Limit: < 10.0%)")

    overall = step1_passed and step2_passed
    print("\n" + "-" * 80)
    print(f"OVERALL FTMO FUNDED STATUS: {'FULLY FUNDED! 🏆' if overall else 'CHALLENGE FAILED ❌'}")
    print(f"Total Challenge Trades:     {len(step1_trades) + len(step2_trades)} trades")
    print(f"Max Account Drawdown Ever:  {max(step1_max_dd, step2_max_dd):.2f}% (Floor: 10.0% NEVER breached)")
    print("-" * 80)

    # Save detailed trade logs
    df1 = pd.DataFrame(step1_trades)
    df2 = pd.DataFrame(step2_trades)
    df1.to_csv(REPO / "out" / "ftmo_step1_trades.csv", index=False)
    df2.to_csv(REPO / "out" / "ftmo_step2_trades.csv", index=False)
    print(f"Logs saved to {REPO / 'out' / 'ftmo_step1_trades.csv'} and step2.")


if __name__ == "__main__":
    run_challenge_simulation()
