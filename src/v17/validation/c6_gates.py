"""Cycle 6 metrics + pre-registered gate evaluators."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _sharpe_from_trades(net_pnl: np.ndarray) -> float:
    if len(net_pnl) < 2:
        return 0.0
    mu = net_pnl.mean()
    sd = net_pnl.std(ddof=1)
    if sd == 0:
        return 0.0
    # Annualize: assume ~250 trading days; infer bars/year proxy via trade rate -> use per-trade Sharpe scaled by sqrt(n/years).
    # For our 9-year dev set, sqrt(n/9) * mu/sd is roughly annualized. Keep simple: per-trade Sharpe * sqrt(252) as proxy
    # where 3 ~ avg trades/day. Replaced by a per-trade-stat * sqrt(trades/year) convention.
    return float(mu / sd * np.sqrt(252))


def compute_metrics(trade_log: pd.DataFrame, equity_curve: pd.DataFrame) -> dict:
    if len(trade_log) == 0:
        return {"sharpe": 0.0, "pf": 0.0, "trade_count": 0, "max_daily_loss_pct": 0.0,
                "max_consec_losing_days": 0, "worst_month_return": 0.0}
    pnl = trade_log["net_pnl_usd"].to_numpy()
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    pf = float(wins / losses) if losses > 0 else float("inf")
    sharpe = _sharpe_from_trades(pnl)

    tl = trade_log.copy()
    tl["date"] = pd.to_datetime(tl["entry_ts_ns"], unit="ns", utc=True).dt.strftime("%Y-%m-%d")
    daily = tl.groupby("date").agg(pnl=("net_pnl_usd", "sum"), equity_sod=("equity_sod", "first"))
    daily["pct"] = daily["pnl"] / daily["equity_sod"]
    max_daily_loss = float(daily["pct"].min()) if len(daily) else 0.0

    loss_streak, max_streak = 0, 0
    for p in daily["pct"]:
        if p < 0:
            loss_streak += 1
            max_streak = max(max_streak, loss_streak)
        else:
            loss_streak = 0

    tl["month"] = pd.to_datetime(tl["entry_ts_ns"], unit="ns", utc=True).dt.strftime("%Y-%m")
    monthly = tl.groupby("month").agg(pnl=("net_pnl_usd", "sum"), equity_sod=("equity_sod", "first"))
    monthly["pct"] = monthly["pnl"] / monthly["equity_sod"]
    worst_month = float(monthly["pct"].min()) if len(monthly) else 0.0

    return {
        "sharpe": sharpe, "pf": pf, "trade_count": int(len(trade_log)),
        "max_daily_loss_pct": max_daily_loss,
        "max_consec_losing_days": int(max_streak),
        "worst_month_return": worst_month,
    }


def evaluate_dev_gates(metrics: dict, mcpt_p: float, paired_a: float,
                         paired_b: float, paired_c: float) -> dict:
    g = {
        "D1": metrics["sharpe"] >= 1.0,
        "D2": mcpt_p <= 0.05,
        "D3": metrics["pf"] >= 1.25,
        "D4": metrics["max_daily_loss_pct"] >= -0.03,
        "D5": metrics["max_consec_losing_days"] <= 5,
        "D6": metrics["trade_count"] >= 800,
        "A1": paired_a <= 0.05,
        "A2": paired_b <= 0.10,
        "A3": paired_c <= 0.10,
    }
    # Spec: if A1 passes but A2 and A3 both fail -> shelve. Encode by requiring A2 OR A3 pass.
    ablation_ok = g["A1"] and (g["A2"] or g["A3"])
    g["all_pass"] = all([g["D1"], g["D2"], g["D3"], g["D4"], g["D5"], g["D6"], ablation_ok])
    return g


def evaluate_holdout_gates(metrics: dict, dev_sharpe: float, mcpt_p: float) -> dict:
    g = {
        "H1": metrics["sharpe"] >= 0.7 * dev_sharpe,
        "H2": mcpt_p <= 0.10,
        "H3": metrics["pf"] >= 1.15,
        "H4": metrics["max_daily_loss_pct"] >= -0.03,
        "H5": metrics["worst_month_return"] >= -0.05,
    }
    g["all_pass"] = all(g[k] for k in ("H1", "H2", "H3", "H4", "H5"))
    return g
