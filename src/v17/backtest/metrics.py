from __future__ import annotations

import math
from decimal import Decimal

import pandas as pd


def profit_factor(trades: list[Decimal]) -> float:
    wins = sum((t for t in trades if t > 0), start=Decimal("0"))
    losses = sum((-t for t in trades if t < 0), start=Decimal("0"))
    if losses == 0:
        return 0.0 if wins == 0 else float("inf")
    return float(wins / losses)


def winrate(trades: list[Decimal]) -> float:
    if not trades:
        return 0.0
    return sum(1 for t in trades if t > 0) / len(trades)


def max_drawdown_pct(equity: list[Decimal]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    worst = 0.0
    for e in equity:
        peak = max(peak, e)
        if peak > 0:
            dd = float((peak - e) / peak * 100)
            worst = max(worst, dd)
    return worst


def sharpe(daily_returns: list[float], periods_per_year: int = 252) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    var = sum((x - mean) ** 2 for x in daily_returns) / (len(daily_returns) - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return mean / std * math.sqrt(periods_per_year)


def daily_returns_from_equity(curve: pd.DataFrame) -> list[float]:
    eq = curve["equity"].astype(float).to_numpy()
    if len(eq) < 2:
        return []
    rets = (eq[1:] - eq[:-1]) / eq[:-1]
    return [float(x) for x in rets]
