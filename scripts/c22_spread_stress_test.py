"""Cycle 22 — Spread Stress Test (RULES.md R19 Conformance).

Evaluates the 4-Pillar Portfolio under adverse broker execution conditions:
1. Baseline: Normal broker spread, slippage, and commissions.
2. Stress Tier 1 (+50% Cost Inflation = 1.5x Spread & Slippage).
3. Stress Tier 2 (+100% Cost Inflation = 2.0x Spread & Slippage - Severe Widening).

Required by RULES.md R19: Strategy must maintain positive expectancy and PF > 1.0 at +50% inflation.
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df, compute_metrics  # noqa: E402
from v17.setups import c22_silver_bullet as sb  # noqa: E402

PERIOD = ("2021-01-01", "2024-12-31")


def scale_bars_spread(b: sb.Bars, mult: float) -> sb.Bars:
    """Inflates bid-ask spread by multiplier `mult` around mid price (RULES.md R19)."""
    if mult == 1.0:
        return b
        
    half_spread = (b.ask_c - b.bid_c) / 2.0 * mult
    
    bid_o = b.mid_o - half_spread
    bid_h = b.mid_h - half_spread
    bid_l = b.mid_l - half_spread
    bid_c = b.mid_c - half_spread
    
    ask_o = b.mid_o + half_spread
    ask_h = b.mid_h + half_spread
    ask_l = b.mid_l + half_spread
    ask_c = b.mid_c + half_spread
    
    return sb.Bars(
        ts=b.ts,
        bid_o=bid_o, bid_h=bid_h, bid_l=bid_l, bid_c=bid_c,
        ask_o=ask_o, ask_h=ask_h, ask_l=ask_l, ask_c=ask_c,
        mid_o=b.mid_o, mid_h=b.mid_h, mid_l=b.mid_l, mid_c=b.mid_c,
        atr=b.atr,
    )


def run_portfolio_under_multiplier(
    bars_cache: dict[str, sb.Bars],
    cal_df: pd.DataFrame,
    mult: float,
) -> dict[str, object]:
    """Runs the 4-pillar portfolio with spread and slippage scaled by `mult`."""
    # 1. Scale bars and specs
    # GBPUSD London Killzone
    b_gbp = scale_bars_spread(bars_cache["GBPUSD"], mult)
    sp_gbp = sb.Spec(
        min_stop=0.0008,
        max_stop=0.0035,
        slip=0.00005 * mult,
        commission_rt=0.00006,
    )
    sb.SPECS["GBPUSD"] = sp_gbp
    sb.WINDOWS["LDN_KZ"] = ((2, 0), (5, 0))
    sb.SESSION_ENDS["LDN_KZ"] = (8, 0)
    t_gbp = sb.run_slot_c22(b_gbp, "GBPUSD", "LDN_KZ", *PERIOD, cal_df)
    t_gbp["pillar"] = "GBPUSD_LDN"
    
    # EURUSD NY AM
    b_eur = scale_bars_spread(bars_cache["EURUSD"], mult)
    sp_eur = sb.Spec(
        min_stop=0.0006,
        max_stop=0.0025,
        slip=0.00005 * mult,
        commission_rt=0.00006,
    )
    sb.SPECS["EURUSD"] = sp_eur
    t_eur = sb.run_slot_c22(b_eur, "EURUSD", "AM", *PERIOD, cal_df)
    t_eur["pillar"] = "EURUSD_AM"
    
    # NQ NY AM
    b_nq = scale_bars_spread(bars_cache["USATECHIDXUSD"], mult)
    sp_nq = sb.Spec(
        min_stop=8.0,
        max_stop=50.0,
        slip=0.5 * mult,
        commission_rt=0.0,
    )
    sb.SPECS["USATECHIDXUSD"] = sp_nq
    t_nq = sb.run_slot_c22(b_nq, "USATECHIDXUSD", "AM", *PERIOD, cal_df)
    t_nq["pillar"] = "NQ_AM"
    
    # ES NY AM
    b_es = scale_bars_spread(bars_cache["USA500IDXUSD"], mult)
    sp_es = sb.Spec(
        min_stop=1.5,
        max_stop=15.0,
        slip=0.5 * mult,
        commission_rt=0.0,
    )
    sb.SPECS["USA500IDXUSD"] = sp_es
    t_es = sb.run_slot_c22(b_es, "USA500IDXUSD", "AM", *PERIOD, cal_df)
    t_es["pillar"] = "ES_AM"
    
    combined = pd.concat([t_gbp, t_eur, t_nq, t_es], ignore_index=True)
    m = compute_metrics(combined)
    return {
        "mult": mult,
        "trades": m["n"],
        "monthly": round(m["n"] / 48.0, 2),
        "win_rate": round(m["win_rate"] * 100, 1),
        "pf": round(m["pf"], 2),
        "mean_r": round(m["mean_r"], 3),
        "max_dd_r": round(m["max_dd_r"], 1),
    }


def main() -> int:
    print("=" * 80)
    print("CYCLE 22: SPREAD & SLIPPAGE STRESS TEST (RULES.md R19)")
    print("Evaluating resilience against broker cost inflation: 1.0x, 1.5x (+50%), 2.0x (+100%)")
    print("=" * 80)
    
    cal_df = load_calendar_blackout_df()
    symbols = ["GBPUSD", "EURUSD", "USATECHIDXUSD", "USA500IDXUSD"]
    bars_cache = {}
    for s in symbols:
        print(f"Loading M1 bars for {s}...")
        df = load_m1_symbol(s)
        bars_cache[s] = sb.prepare(df)
        
    tiers = [1.0, 1.5, 2.0]
    results = []
    
    for mult in tiers:
        tag = "Baseline (1.0x)" if mult == 1.0 else (f"Stress Tier 1 (+50% / {mult:.1f}x)" if mult == 1.5 else f"Stress Tier 2 (+100% / {mult:.1f}x)")
        print(f"\nRunning {tag}...")
        res = run_portfolio_under_multiplier(bars_cache, cal_df, mult)
        res["Tier"] = tag
        results.append(res)
        print(f"  Trades: {res['trades']} ({res['monthly']}/mo) | WinRate: {res['win_rate']}% | PF: {res['pf']:.2f} | MeanR: {res['mean_r']:+.3f}R | DD: {res['max_dd_r']:.1f}R")
        
    print("\n" + "=" * 80)
    print("=== SPREAD STRESS TEST MATRIX (RULES.md R19 VERDICT) ===")
    print("=" * 80)
    df_res = pd.DataFrame(results)[["Tier", "trades", "monthly", "win_rate", "pf", "mean_r", "max_dd_r"]]
    df_res.columns = ["Cost Multiplier Tier", "Trades (n)", "Trades/Mo", "WinRate %", "Profit Factor", "Mean Return", "Max DD (R)"]
    print(df_res.to_string(index=False))
    
    # Check compliance with RULES.md R19
    tier1_pf = results[1]["pf"]
    tier2_pf = results[2]["pf"]
    tier1_pass = tier1_pf >= 1.0
    tier2_pass = tier2_pf >= 1.0
    
    print("\n" + "-" * 80)
    print(f"Gate 1: +50% Spread Inflation PF ({tier1_pf:.2f} >= 1.00):  {'PASS' if tier1_pass else 'FAIL'}")
    print(f"Gate 2: +100% Spread Inflation PF ({tier2_pf:.2f} >= 1.00): {'PASS' if tier2_pass else 'FAIL'}")
    print("-" * 80)
    
    overall = tier1_pass and tier2_pass
    verdict = "PASS (DURABLE UNDER ADVERSE BROKER CONDITIONS)" if overall else ("PASS TIER 1 ONLY" if tier1_pass else "FAIL (FRAGILE)")
    print(f"FINAL R19 VERDICT: {verdict}")
    print("=" * 80)
    
    (REPO / "out" / "c22_spread_stress_test.txt").write_text(df_res.to_string(index=False), encoding="utf-8")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
