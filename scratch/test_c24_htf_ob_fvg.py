"""Quick evaluation of Cycle 24 HTF Order Block + LTF FVG Confluence (Sliced)."""

from pathlib import Path
import sys
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from run_c22_silver_bullet import load_m1_symbol  # noqa: E402
from v17.setups import c22_silver_bullet as sb  # noqa: E402
from v17.setups.c24_htf_ob_ltf_fvg import scan_htf_ob_ltf_fvg_trades, SPECS  # noqa: E402


def evaluate(sym: str) -> None:
    print(f"\n=======================================================")
    print(f"EVALUATING CYCLE 24: HTF OB + LTF FVG on {sym}")
    print(f"Period: 2021-01-01 to 2024-12-31")
    print(f"=======================================================")

    raw_df = load_m1_symbol(sym)
    b_full = sb.prepare(raw_df)

    # Slice to 2020-09-01 -> 2024-12-31 (includes H1 warmup)
    ts_dt = pd.to_datetime(b_full.ts, unit="ns", utc=True)
    mask = (ts_dt >= pd.Timestamp("2020-09-01", tz="UTC")) & (ts_dt <= pd.Timestamp("2024-12-31 23:59:59", tz="UTC"))
    idx = np.where(mask)[0]
    i0, i1 = idx[0], idx[-1] + 1

    trades_df = scan_htf_ob_ltf_fvg_trades(
        b_m1_ts=b_full.ts[i0:i1],
        b_m1_bid_o=b_full.bid_o[i0:i1], b_m1_bid_h=b_full.bid_h[i0:i1],
        b_m1_bid_l=b_full.bid_l[i0:i1], b_m1_bid_c=b_full.bid_c[i0:i1],
        b_m1_ask_o=b_full.ask_o[i0:i1], b_m1_ask_h=b_full.ask_h[i0:i1],
        b_m1_ask_l=b_full.ask_l[i0:i1], b_m1_ask_c=b_full.ask_c[i0:i1],
        b_m1_mid_o=b_full.mid_o[i0:i1], b_m1_mid_h=b_full.mid_h[i0:i1],
        b_m1_mid_l=b_full.mid_l[i0:i1], b_m1_mid_c=b_full.mid_c[i0:i1],
        symbol=sym,
        sp=SPECS[sym],
        start_date="2021-01-01",
        end_date="2024-12-31",
        target_rr=2.0,
    )

    if len(trades_df) == 0:
        print(f"[{sym}] 0 trades found.")
        return

    n_trades = len(trades_df)
    wins = trades_df[trades_df["r"] > 0]
    losses = trades_df[trades_df["r"] <= 0]
    wr = len(wins) / n_trades * 100.0

    gross_win = wins["r"].sum()
    gross_loss = abs(losses["r"].sum())
    pf = gross_win / gross_loss if gross_loss > 0 else 999.0
    net_r = trades_df["r"].sum()
    avg_r = trades_df["r"].mean()

    cum_r = trades_df["r"].cumsum()
    peak = cum_r.cummax()
    dd = peak - cum_r
    max_dd = dd.max()

    print(f"\n[{sym}] RESULTS (2021-2024):")
    print(f"  Total Trades:     {n_trades}")
    print(f"  Win Rate:         {wr:.1f}% ({len(wins)}W / {len(losses)}L)")
    print(f"  Profit Factor:    {pf:.2f}")
    print(f"  Net R:            {net_r:+.2f} R")
    print(f"  Mean R/trade:     {avg_r:+.3f} R")
    print(f"  Max Drawdown:     {max_dd:.2f} R")
    print("\nFirst 5 trades:")
    print(trades_df[["day", "side", "entry", "sl", "tp", "r", "reason"]].head(5))


if __name__ == "__main__":
    evaluate("EURUSD")
    evaluate("GBPUSD")
