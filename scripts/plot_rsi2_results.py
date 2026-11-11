"""Plot RSI2-NAS100 dev + holdout trade performance to PNG.

Produces two PNGs in out/c4b_gates/:
  rsi2_dev_results.png
  rsi2_holdout_results.png

Each figure: top panel = price with entry (green up-triangle) and exit
(red down-triangle) markers; bottom panel = cumulative pnl_r curve.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.backtest.rsi2_runner import run_rsi2_oos_batch
from v17.backtest.walkforward import Fold, generate_folds
from v17.data.parquet_store import read_bars_d1
from v17.setups.rsi2_engines import RSI2_CATALOG


def _plot_window(bars, trades, title: str, out_path: Path) -> None:
    ts = pd.to_datetime(bars["ts_utc"], unit="ns", utc=True)
    mid = (bars["bid_c"] + bars["ask_c"]) / 2

    fig, (ax_p, ax_e) = plt.subplots(
        2, 1, figsize=(14, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    ax_p.plot(ts, mid, color="#1f77b4", linewidth=0.8, label="USATECHIDXUSD mid")
    ax_p.set_ylabel("price")
    ax_p.set_title(title)
    ax_p.grid(alpha=0.3)

    if trades:
        tr = pd.DataFrame(trades)
        entry_ts = pd.to_datetime(tr["ts_entry_ns"], unit="ns", utc=True)
        exit_ts = pd.to_datetime(tr["ts_exit_ns"], unit="ns", utc=True)
        ax_p.scatter(entry_ts, tr["entry_price"], marker="^", color="green",
                     s=40, zorder=5, label=f"entry ({len(tr)})")
        ax_p.scatter(exit_ts, tr["exit_price"], marker="v", color="red",
                     s=40, zorder=5, label=f"exit ({len(tr)})")

        # Cumulative pnl_r plot.
        cum = tr["pnl_r"].cumsum()
        ax_e.plot(exit_ts, cum, color="purple", linewidth=1.2, marker="o", markersize=3)
        wins = tr[tr["pnl_r"] > 0]
        losses = tr[tr["pnl_r"] < 0]
        pf = wins["pnl_r"].sum() / abs(losses["pnl_r"].sum()) if len(losses) else float("inf")
        wr = (tr["pnl_r"] > 0).mean()
        avg_r = tr["pnl_r"].mean()
        ax_e.set_ylabel("cumulative pnl (R)")
        ax_e.grid(alpha=0.3)
        ax_e.axhline(0, color="k", linewidth=0.5)
        ax_e.text(
            0.01, 0.97,
            f"trades: {len(tr)}   PF: {pf:.2f}   WR: {wr:.1%}   avg_r: {avg_r:+.3f}",
            transform=ax_e.transAxes, verticalalignment="top",
            fontsize=10, family="monospace",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.85),
        )

    ax_p.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"wrote {out_path}", flush=True)


def main() -> None:
    engine = RSI2_CATALOG[0]
    out_dir = Path("out/c4b_gates")

    # DEV
    bars_dev = read_bars_d1(engine.symbol, "dev")
    folds = generate_folds()
    logs = run_rsi2_oos_batch(engine, bars_dev, folds)
    dev_trades = [t for l in logs for t in l.trades]
    _plot_window(
        bars_dev, dev_trades,
        f"RSI2-{engine.symbol} dev — 7-fold OOS 2018-2024",
        out_dir / "rsi2_dev_results.png",
    )

    # HOLDOUT
    bars_ho = read_bars_d1(engine.symbol, "holdout")
    ho_start = pd.Timestamp("2025-01-01", tz="UTC").value
    ho_end = pd.Timestamp("2026-10-19", tz="UTC").value
    fold_ho = Fold(fold_id=100, train_start=0, train_end=ho_start - 1,
                   oos_start=ho_start, oos_end=ho_end)
    logs = run_rsi2_oos_batch(engine, bars_ho, [fold_ho])
    ho_trades = [t for l in logs for t in l.trades]
    _plot_window(
        bars_ho, ho_trades,
        f"RSI2-{engine.symbol} holdout (sealed) 2025-01-01 → 2026-10-18",
        out_dir / "rsi2_holdout_results.png",
    )


if __name__ == "__main__":
    main()
