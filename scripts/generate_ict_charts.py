"""Generate Standalone Interactive TradingView Charts for EURUSD & GBPUSD.

Visualizes continuous M5 market structure:
- Shaded FVGs (active until mitigated)
- Shaded Order Blocks (active until invalidated)
- Liquidity sweeps & Asian / Killzone levels
- Verified FTMO Silver Bullet trades with Entry, SL, TP, and Net R.
"""

from __future__ import annotations

from pathlib import Path
import sys
import time
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol, load_calendar_blackout_df  # noqa: E402
from v17.setups import c22_silver_bullet as sb  # noqa: E402
from v17.viz.ict_state_machine import extract_continuous_ict_state  # noqa: E402
from v17.viz.chart_builder import build_interactive_chart  # noqa: E402

OUTPUT_DIR = REPO / "out" / "charts"
START_DATE = "2021-01-01"
END_DATE = "2024-12-31"


def generate_for_symbol(symbol: str, window: str, min_stop: float, title_suffix: str) -> Path:
    t0 = time.time()
    print(f"\n" + "=" * 75)
    print(f"Generating Continuous ICT Chart for {symbol} ({title_suffix})")
    print(f"Period: {START_DATE} to {END_DATE}")
    print("=" * 75)

    cal_df = load_calendar_blackout_df()

    # 1. Load M1 Data
    print(f"[{symbol}] Loading M1 bars from disk...")
    raw_df = load_m1_symbol(symbol)
    b_full = sb.prepare(raw_df)

    # 2. Slice to the Evaluation Window (2021 - 2024)
    print(f"[{symbol}] Slicing to evaluation period {START_DATE} -> {END_DATE}...")
    ts_dt = pd.to_datetime(b_full.ts, unit="ns", utc=True)
    t_start = pd.Timestamp(START_DATE, tz="UTC")
    t_end = pd.Timestamp(END_DATE + " 23:59:59", tz="UTC")
    mask_eval = (ts_dt >= t_start) & (ts_dt <= t_end)
    eval_indices = np.where(mask_eval)[0]

    i_lo, i_hi = eval_indices[0], eval_indices[-1] + 1
    b_eval = sb.Bars(
        ts=b_full.ts[i_lo:i_hi],
        bid_o=b_full.bid_o[i_lo:i_hi], bid_h=b_full.bid_h[i_lo:i_hi],
        bid_l=b_full.bid_l[i_lo:i_hi], bid_c=b_full.bid_c[i_lo:i_hi],
        ask_o=b_full.ask_o[i_lo:i_hi], ask_h=b_full.ask_h[i_lo:i_hi],
        ask_l=b_full.ask_l[i_lo:i_hi], ask_c=b_full.ask_c[i_lo:i_hi],
        mid_o=b_full.mid_o[i_lo:i_hi], mid_h=b_full.mid_h[i_lo:i_hi],
        mid_l=b_full.mid_l[i_lo:i_hi], mid_c=b_full.mid_c[i_lo:i_hi],
        atr=b_full.atr[i_lo:i_hi],
    )

    # 3. Aggregate to M5
    print(f"[{symbol}] Aggregating {len(b_eval.ts):,} M1 bars to M5...")
    m5 = sb.build_m5(b_eval)
    print(f"[{symbol}] Built {len(m5.ts_start):,} continuous M5 bars.")

    # 4. Extract Stateful ICT Primitives
    print(f"[{symbol}] Vectorized extraction of FVGs, Order Blocks, and Liquidity Sweeps...")
    t_ict = time.time()
    chart_data = extract_continuous_ict_state(
        b_ts=m5.ts_start,
        b_o=m5.o,
        b_h=m5.h,
        b_l=m5.l,
        b_c=m5.c,
        symbol=symbol,
        min_fvg_pips=0.00015 if "USD" in symbol else 1.0,
        max_active_lookforward=300,
    )
    print(f"[{symbol}] Extracted in {time.time()-t_ict:.2f}s: {len(chart_data['fvgs']):,} FVGs, {len(chart_data['order_blocks']):,} OBs, {len(chart_data['sessions']):,} Sessions, {len(chart_data['liquidity_levels']):,} Liquidity levels.")

    # 5. Run and map verified Silver Bullet trades
    print(f"[{symbol}] Running verified Silver Bullet setup engine...")
    sb.SPECS[symbol] = sb.Spec(min_stop=min_stop, max_stop=0.0035 if "GBP" in symbol else 0.0025, slip=0.00005, commission_rt=0.00006)
    if window == "LDN_SB":
        sb.WINDOWS["LDN_SB"] = ((3, 0), (4, 0))
        sb.SESSION_ENDS["LDN_SB"] = (8, 0)

    trades_df = sb.run_slot_c22(b_full, symbol, window, START_DATE, END_DATE, cal_df)
    print(f"[{symbol}] Found {len(trades_df)} verified Silver Bullet trades.")

    trades_list = []
    for _, tr in trades_df.iterrows():
        fill_i = int(tr["fill_i"])
        exit_i = int(tr["exit_i"]) if tr["exit_i"] is not None and not np.isnan(tr["exit_i"]) else None

        fill_time = int(b_full.ts[fill_i] // 1_000_000_000)
        exit_time = int(b_full.ts[exit_i] // 1_000_000_000) if exit_i is not None else None

        trades_list.append({
            "day": str(tr["day"]),
            "symbol": symbol,
            "window": window,
            "pillar": f"{symbol}_{window}",
            "side": int(tr["side"]),
            "entry": float(tr["entry"]),
            "sl": float(tr["sl"]),
            "tp": float(tr["tp"]),
            "fill_time": fill_time,
            "exit_time": exit_time,
            "r": float(tr["r"]),
            "reason": str(tr["reason"]),
        })

    # 6. Build HTML File
    out_file = OUTPUT_DIR / f"ict_continuous_{symbol.lower()}.html"
    build_interactive_chart(
        chart_data=chart_data,
        trades=trades_list,
        symbol=symbol,
        output_path=out_file,
        title=f"ICT Continuous Market Structure & Silver Bullet — {symbol} ({title_suffix})",
    )
    print(f"[{symbol}] Completed in {time.time()-t0:.2f}s. Chart saved to:\n     --> {out_file.resolve()}")
    return out_file


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. EURUSD NY AM
    eur_html = generate_for_symbol(
        symbol="EURUSD",
        window="AM",
        min_stop=0.0006,
        title_suffix="NY AM Opening Drive",
    )

    # 2. GBPUSD London Silver Bullet
    gbp_html = generate_for_symbol(
        symbol="GBPUSD",
        window="LDN_SB",
        min_stop=0.0015,
        title_suffix="London Killzone Silver Bullet",
    )

    print("\n" + "=" * 80)
    print("ALL INTERACTIVE ICT CHARTS GENERATED SUCCESSFULLY!")
    print(f"1. EURUSD: {eur_html.resolve()}")
    print(f"2. GBPUSD: {gbp_html.resolve()}")
    print("=" * 80)


if __name__ == "__main__":
    main()
