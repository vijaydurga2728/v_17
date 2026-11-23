"""Cycle 22 — Monte Carlo Permutation Test (MCPT Scheme 1).

Tests whether the observed positive expectancy of the Institutional Silver Bullet on
NY AM EURUSD (2021-2026) is statistically significant against 5,000 matched random entries
drawn from the same session windows on identical price bars.
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

try:
    from numba import njit
except ImportError:  # pragma: no cover
    def njit(*a, **k):  # type: ignore[no-redef]
        return (lambda f: f) if not (a and callable(a[0])) else a[0]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df  # noqa: E402
from v17.setups import c22_silver_bullet as sb  # noqa: E402


@njit(cache=False)
def _null_mcpt_core(
    n_perms: int,
    seeds: np.ndarray,
    ws_indices: np.ndarray,
    we_indices: np.ndarray,
    sess_ends: np.ndarray,
    sides: np.ndarray,
    risk_dists: np.ndarray,
    tp_dists: np.ndarray,
    slip: float,
    comm: float,
    bid_o: np.ndarray,
    bid_h: np.ndarray,
    bid_l: np.ndarray,
    bid_c: np.ndarray,
    ask_o: np.ndarray,
    ask_h: np.ndarray,
    ask_l: np.ndarray,
    ask_c: np.ndarray,
) -> np.ndarray:
    n_trades = len(sides)
    n_days = len(ws_indices)
    null_means = np.empty(n_perms, dtype=np.float64)
    
    for p in range(n_perms):
        np.random.seed(seeds[p])
        perm_sides = sides[np.random.permutation(n_trades)]
        tot_r = 0.0
        
        for t in range(n_trades):
            # Pick a random day's window
            d_idx = np.random.randint(0, n_days)
            ws_i = ws_indices[d_idx]
            we_i = we_indices[d_idx]
            end_i = sess_ends[d_idx]
            if we_i <= ws_i:
                continue
                
            # Random entry bar in window
            entry_i = np.random.randint(ws_i, we_i)
            side = perm_sides[t]
            dist = risk_dists[t]
            tp_dist = tp_dists[t]
            
            entry_px = (ask_o[entry_i] + slip) if side == 1 else (bid_o[entry_i] - slip)
            sl_px = entry_px - side * dist
            tp_px = entry_px + side * tp_dist
            
            # Execute random trade
            exit_i, reason, raw_exit = sb.execute_trade_m1(
                entry_i, end_i, side, sl_px, tp_px,
                bid_o, bid_h, bid_l, bid_c,
                ask_o, ask_h, ask_l, ask_c
            )
            
            s = slip if reason != 2 else 0.0
            px = raw_exit - s if side == 1 else raw_exit + s
            pnl = (px - entry_px) * side - comm
            tot_r += pnl / dist
            
        null_means[p] = tot_r / n_trades
        
    return null_means


def main() -> int:
    print("=" * 70)
    print("CYCLE 22: MONTE CARLO PERMUTATION TEST (MCPT SCHEME 1)")
    print("Asset: EURUSD | Session: NY AM (10:00 - 11:00 NY) | 2021 - 2026")
    print("=" * 70)
    
    cal_df = load_calendar_blackout_df()
    df_m1 = load_m1_symbol("EURUSD")
    b = sb.prepare(df_m1)
    
    # Run full 2021-2026 slot with min_stop=6.0 pips
    sb.SPECS["EURUSD"] = sb.Spec(min_stop=0.0006, max_stop=0.0025, slip=0.00005, commission_rt=0.00006)
    trades = sb.run_slot_c22(b, "EURUSD", "AM", "2021-01-01", "2026-12-31", cal_df)
    
    if trades.empty:
        print("ERROR: No trades generated for AM EURUSD.")
        return 1
        
    n_trades = len(trades)
    obs_mean_r = float(trades["r"].mean())
    win_rate = float((trades["r"] > 0).mean())
    tot_win = float(trades[trades["r"] > 0]["r"].sum())
    tot_loss = float(-trades[trades["r"] < 0]["r"].sum())
    pf = tot_win / tot_loss if tot_loss > 0 else float("inf")
    
    print(f"Observed Strategy Performance (2021-2026):")
    print(f"  Total Trades (n):  {n_trades}")
    print(f"  Win Rate:          {win_rate * 100:.1f}%")
    print(f"  Profit Factor:     {pf:.2f}")
    print(f"  Observed Mean R:   {obs_mean_r:+.4f}R")
    
    # Build day window boundaries for random sampler
    days = pd.date_range("2021-01-01", "2026-12-31", freq="B")
    ws_list, we_list, end_list = [], [], []
    (sh, sm), (eh, em) = sb.WINDOWS["AM"]
    (end_h, end_m) = sb.SESSION_ENDS["AM"]
    
    for d in days:
        d0_ns = pd.Timestamp(d.date()).tz_localize(sb.NY).tz_convert("UTC").value
        ws_ns = d0_ns + (sh * 3600 + sm * 60) * 1_000_000_000
        we_ns = d0_ns + (eh * 3600 + em * 60) * 1_000_000_000
        sess_end_ns = d0_ns + (end_h * 3600 + end_m * 60) * 1_000_000_000
        
        i_ws = np.searchsorted(b.ts, ws_ns)
        i_we = np.searchsorted(b.ts, we_ns)
        i_end = np.searchsorted(b.ts, sess_end_ns)
        
        if i_we > i_ws + 5 and i_end > i_we:
            ws_list.append(i_ws)
            we_list.append(i_we)
            end_list.append(i_end)
            
    ws_indices = np.array(ws_list, dtype=np.int64)
    we_indices = np.array(we_list, dtype=np.int64)
    sess_ends = np.array(end_list, dtype=np.int64)
    
    # 5,000 permutations
    n_perms = 5_000
    seeds = np.array([np.random.SeedSequence([42, j]).generate_state(1)[0] for j in range(n_perms)], dtype=np.int64) % (2**31 - 1)
    
    sides = trades["side"].to_numpy(np.int64)
    risk_dists = trades["risk_dist"].to_numpy(np.float64)
    tp_dists = (trades["risk_dist"] * 2.0).to_numpy(np.float64) # 2.0R target
    
    sp = sb.SPECS["EURUSD"]
    print(f"\nRunning {n_perms:,} Monte Carlo Permutations against matched random baseline...")
    
    null_dist = _null_mcpt_core(
        n_perms,
        seeds,
        ws_indices,
        we_indices,
        sess_ends,
        sides,
        risk_dists,
        tp_dists,
        sp.slip,
        sp.commission_rt,
        b.bid_o, b.bid_h, b.bid_l, b.bid_c,
        b.ask_o, b.ask_h, b.ask_l, b.ask_c,
    )
    
    null_median = float(np.median(null_dist))
    null_95th = float(np.percentile(null_dist, 95))
    e = int((null_dist >= obs_mean_r).sum())
    p_val = (e + 1) / (n_perms + 1)
    
    print("\nMCPT Scheme 1 Statistical Verdict:")
    print(f"  Null Median Mean R:  {null_median:+.4f}R (drag from spread & commission)")
    print(f"  Null 95th Percentile: {null_95th:+.4f}R")
    print(f"  Observed Mean R:      {obs_mean_r:+.4f}R")
    print(f"  Permutations >= Obs:  {e} / {n_perms}")
    print(f"  Empirical p-value:    p = {p_val:.5f}")
    
    passed = p_val < 0.05
    verdict_str = "PASS (Statistically Significant Alpha)" if passed else "FAIL (Not distinguishable from luck)"
    print(f"\n  Final Standard: p < 0.05 => {verdict_str}")
    print("=" * 70)
    
    # Save MCPT result log
    log_text = (
        f"MCPT Scheme 1: EURUSD AM 2021-2026\n"
        f"n={n_trades} PF={pf:.2f} win={win_rate*100:.1f}%\n"
        f"Observed={obs_mean_r:+.4f}R NullMedian={null_median:+.4f}R p={p_val:.5f} PASS={passed}\n"
    )
    (REPO / "out" / "c22" / "mcpt_eurusd_am.txt").write_text(log_text, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
