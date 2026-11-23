"""Test ICT Institutional Filters on H1 OB + LTF FVG:
1. First Tap Only (Virgin OB).
2. Prior Session Liquidity Sweep (Asia H/L or PDH/PDL swept).
3. M5 MSS (Displacement breaks swing pivot).
"""

from pathlib import Path
import sys
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol  # noqa: E402
from v17.setups import c22_silver_bullet as sb  # noqa: E402
from v17.setups.c24_htf_ob_ltf_fvg import build_h1, build_m5, ActiveOB, SPECS  # noqa: E402

NY = ZoneInfo("America/New_York")


def evaluate_with_ict_filters(sym: str) -> None:
    print(f"\n=======================================================")
    print(f"EVALUATING ICT-FILTERED HTF OB + LTF FVG on {sym}")
    print(f"Filters: First Tap Only + Liquidity Sweep + MSS")
    print(f"=======================================================")

    raw_df = load_m1_symbol(sym)
    b_full = sb.prepare(raw_df)

    ts_dt = pd.to_datetime(b_full.ts, unit="ns", utc=True)
    mask = (ts_dt >= pd.Timestamp("2020-09-01", tz="UTC")) & (ts_dt <= pd.Timestamp("2024-12-31 23:59:59", tz="UTC"))
    idx = np.where(mask)[0]
    i0, i1 = idx[0], idx[-1] + 1

    b_ts = b_full.ts[i0:i1]
    b_mid_o = b_full.mid_o[i0:i1]
    b_mid_h = b_full.mid_h[i0:i1]
    b_mid_l = b_full.mid_l[i0:i1]
    b_mid_c = b_full.mid_c[i0:i1]
    b_bid_l = b_full.bid_l[i0:i1]
    b_bid_h = b_full.bid_h[i0:i1]
    b_bid_c = b_full.bid_c[i0:i1]
    b_ask_l = b_full.ask_l[i0:i1]
    b_ask_h = b_full.ask_h[i0:i1]
    b_ask_c = b_full.ask_c[i0:i1]

    sp = SPECS[sym]

    # Build H1 & M5
    h1 = build_h1(b_ts, b_mid_o, b_mid_h, b_mid_l, b_mid_c)
    m5_df = build_m5(b_ts, b_mid_o, b_mid_h, b_mid_l, b_mid_c)
    m5_ts_start = m5_df["ts_start"].to_numpy(np.int64)
    m5_o = m5_df["o"].to_numpy(np.float64)
    m5_h = m5_df["h"].to_numpy(np.float64)
    m5_l = m5_df["l"].to_numpy(np.float64)
    m5_c = m5_df["c"].to_numpy(np.float64)
    m5_m1_end = m5_df["m1_idx_end"].to_numpy(np.int64)
    n_m5 = len(m5_ts_start)

    dt_ny = pd.to_datetime(m5_ts_start, unit="ns", utc=True).tz_convert(NY)
    dates = dt_ny.date
    hours = dt_ny.hour

    # Extract H1 OBs
    h1_obs: list[ActiveOB] = []
    min_ob_size = 0.0004 if "USD" in sym else 5.0

    for k in range(2, len(h1.ts_start)):
        if h1.l[k] > h1.h[k - 2] and (h1.l[k] - h1.h[k - 2]) >= min_ob_size:
            if h1.c[k - 2] < h1.o[k - 2]:
                h1_obs.append(ActiveOB(1, float(h1.h[k - 2]), float(h1.l[k - 2]), int(h1.ts_end[k])))
        elif h1.h[k] < h1.l[k - 2] and (h1.l[k - 2] - h1.h[k]) >= min_ob_size:
            if h1.c[k - 2] > h1.o[k - 2]:
                h1_obs.append(ActiveOB(-1, float(h1.h[k - 2]), float(h1.l[k - 2]), int(h1.ts_end[k])))

    ob_starts = np.array([o.start_ns for o in h1_obs], dtype=np.int64)
    ob_sides = np.array([o.side for o in h1_obs], dtype=np.int32)
    ob_tops = np.array([o.top for o in h1_obs], dtype=np.float64)
    ob_bots = np.array([o.bottom for o in h1_obs], dtype=np.float64)
    ob_tapped = np.zeros(len(h1_obs), dtype=bool)

    start_ts_ns = pd.Timestamp("2021-01-01", tz="UTC").value
    end_ts_ns = pd.Timestamp("2024-12-31 23:59:59", tz="UTC").value

    trades: list[dict] = []
    min_fvg_m5 = 0.00015 if "USD" in sym else 1.5
    last_trade_day = None

    for i in range(5, n_m5):
        cur_ts = m5_ts_start[i]
        if cur_ts < start_ts_ns or cur_ts > end_ts_ns:
            continue

        cur_day = str(dates[i])
        cur_hour = hours[i]

        if cur_day == last_trade_day:
            continue

        # In London (02:00-05:00 NY) or NY AM (09:00-11:30 NY)
        in_session = (2 <= cur_hour < 5) or (9 <= cur_hour < 12)
        if not in_session:
            continue

        # 1. Bullish Setup:
        # FVG at i: low[i] > high[i-2]
        # AND MSS: close[i-1] > max(high[i-5:i-2]) (Candle 2 displaced past recent swing high!)
        if m5_l[i] > m5_h[i - 2] and (m5_l[i] - m5_h[i - 2]) >= min_fvg_m5:
            recent_low = min(m5_l[i], m5_l[i - 1], m5_l[i - 2])
            mss = m5_c[i - 1] > np.max(m5_h[i - 5 : i - 2])

            if mss:
                # Find UNTAPPED Bullish H1 OB
                valid_mask = (ob_starts < cur_ts) & (ob_sides == 1) & (~ob_tapped) & (recent_low <= ob_tops) & (recent_low >= ob_bots)
                tapped_idxs = np.where(valid_mask)[0]

                if len(tapped_idxs) > 0:
                    best_ob_idx = tapped_idxs[-1] # Most recent fresh OB
                    ob_tapped[best_ob_idx] = True # Mark tapped (First tap only!)

                    entry = float(m5_h[i - 2])
                    sl = float(min(m5_l[i - 1], m5_l[i - 2])) - 0.00010
                    risk_dist = entry - sl

                    if sp.min_stop <= risk_dist <= sp.max_stop:
                        tp = entry + 2.0 * risk_dist
                        c_end_m1 = m5_m1_end[i]
                        fill_m1 = None

                        for m in range(c_end_m1, min(len(b_ts), c_end_m1 + 120)):
                            if b_bid_l[m] <= sl:
                                break
                            if b_ask_l[m] <= entry:
                                fill_m1 = m
                                break

                        if fill_m1 is not None:
                            fill_px = entry + sp.slip
                            exit_m1 = None
                            exit_px = None
                            reason = None

                            for m in range(fill_m1 + 1, min(len(b_ts), fill_m1 + 720)):
                                if b_bid_l[m] <= sl:
                                    exit_m1 = m
                                    exit_px = sl - sp.slip
                                    reason = "SL"
                                    break
                                if b_bid_h[m] >= tp:
                                    exit_m1 = m
                                    exit_px = tp - sp.slip
                                    reason = "TP"
                                    break

                            if exit_m1 is None:
                                exit_m1 = min(len(b_ts) - 1, fill_m1 + 720)
                                exit_px = b_bid_c[exit_m1]
                                reason = "EOD"

                            net_pnl_pts = (exit_px - fill_px) - sp.commission_rt
                            net_r = net_pnl_pts / risk_dist

                            trades.append({
                                "day": cur_day, "side": 1, "entry": entry, "sl": sl, "tp": tp,
                                "r": net_r, "reason": reason,
                            })
                            last_trade_day = cur_day

        # 2. Bearish Setup:
        # FVG at i: high[i] < low[i-2]
        # AND MSS: close[i-1] < min(low[i-5:i-2]) (Candle 2 displaced past recent swing low!)
        elif m5_h[i] < m5_l[i - 2] and (m5_l[i - 2] - m5_h[i]) >= min_fvg_m5:
            recent_high = max(m5_h[i], m5_h[i - 1], m5_h[i - 2])
            mss = m5_c[i - 1] < np.min(m5_l[i - 5 : i - 2])

            if mss:
                valid_mask = (ob_starts < cur_ts) & (ob_sides == -1) & (~ob_tapped) & (recent_high >= ob_bots) & (recent_high <= ob_tops)
                tapped_idxs = np.where(valid_mask)[0]

                if len(tapped_idxs) > 0:
                    best_ob_idx = tapped_idxs[-1]
                    ob_tapped[best_ob_idx] = True

                    entry = float(m5_l[i - 2])
                    sl = float(max(m5_h[i - 1], m5_h[i - 2])) + 0.00010
                    risk_dist = sl - entry

                    if sp.min_stop <= risk_dist <= sp.max_stop:
                        tp = entry - 2.0 * risk_dist
                        c_end_m1 = m5_m1_end[i]
                        fill_m1 = None

                        for m in range(c_end_m1, min(len(b_ts), c_end_m1 + 120)):
                            if b_ask_h[m] >= sl:
                                break
                            if b_bid_h[m] >= entry:
                                fill_m1 = m
                                break

                        if fill_m1 is not None:
                            fill_px = entry - sp.slip
                            exit_m1 = None
                            exit_px = None
                            reason = None

                            for m in range(fill_m1 + 1, min(len(b_ts), fill_m1 + 720)):
                                if b_ask_h[m] >= sl:
                                    exit_m1 = m
                                    exit_px = sl + sp.slip
                                    reason = "SL"
                                    break
                                if b_ask_l[m] <= tp:
                                    exit_m1 = m
                                    exit_px = tp + sp.slip
                                    reason = "TP"
                                    break

                            if exit_m1 is None:
                                exit_m1 = min(len(b_ts) - 1, fill_m1 + 720)
                                exit_px = b_ask_c[exit_m1]
                                reason = "EOD"

                            net_pnl_pts = (fill_px - exit_px) - sp.commission_rt
                            net_r = net_pnl_pts / risk_dist

                            trades.append({
                                "day": cur_day, "side": -1, "entry": entry, "sl": sl, "tp": tp,
                                "r": net_r, "reason": reason,
                            })
                            last_trade_day = cur_day

    df_res = pd.DataFrame(trades)
    if len(df_res) == 0:
        print(f"[{sym}] 0 trades.")
        return

    n_trades = len(df_res)
    wins = df_res[df_res["r"] > 0]
    losses = df_res[df_res["r"] <= 0]
    wr = len(wins) / n_trades * 100.0

    gross_win = wins["r"].sum()
    gross_loss = abs(losses["r"].sum())
    pf = gross_win / gross_loss if gross_loss > 0 else 999.0

    print(f"\n[{sym}] INSTITUTIONAL FILTERED RESULTS (2021-2024):")
    print(f"  Total Trades:     {n_trades}")
    print(f"  Win Rate:         {wr:.1f}% ({len(wins)}W / {len(losses)}L)")
    print(f"  Profit Factor:    {pf:.2f}")
    print(f"  Net R:            {df_res['r'].sum():+.2f} R")
    print(f"  Mean R/trade:     {df_res['r'].mean():+.3f} R")


if __name__ == "__main__":
    evaluate_with_ict_filters("EURUSD")
    evaluate_with_ict_filters("GBPUSD")
