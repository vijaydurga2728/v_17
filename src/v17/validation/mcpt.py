from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import numpy as np
import pandas as pd

from v17.backtest.loop import EventLoop
from v17.backtest.metrics import profit_factor
from v17.backtest.precompute import precompute
from v17.common.types import Symbol
from v17.risk.engine import DefaultRiskEngine
from v17.setups.judas_swing import JudasSwing
from v17.setups.silver_bullet import SilverBullet


def permute_bars(bars: pd.DataFrame, seed: int | None = None) -> pd.DataFrame:
    """Deconstruct bars into relative intrabar shapes and interbar gaps,
    shuffle them independently to destroy serial market structure, and reconstruct
    synthetic OHLC price bars.

    Based on the Monte Carlo Permutation Testing (MCPT) methodology from
    neurotrader888/mcpt (David Aronson / Timothy Masters).
    """
    if len(bars) < 2:
        return bars.copy()

    rng = np.random.default_rng(seed)
    n_bars = len(bars)

    # 1. Log transform
    log_open = np.log(bars["open"].to_numpy(dtype=np.float64))
    log_high = np.log(bars["high"].to_numpy(dtype=np.float64))
    log_low = np.log(bars["low"].to_numpy(dtype=np.float64))
    log_close = np.log(bars["close"].to_numpy(dtype=np.float64))

    # 2. Extract relative components:
    # Gap from previous close to current open
    rel_gap = log_open[1:] - log_close[:-1]
    # Intrabar excursions relative to open
    rel_high = log_high[1:] - log_open[1:]
    rel_low = log_low[1:] - log_open[1:]
    rel_close = log_close[1:] - log_open[1:]

    perm_n = n_bars - 1
    idx = np.arange(perm_n)

    # 3. Independent permutations:
    # Permute intrabar structure
    perm_intra = rng.permutation(idx)
    shuffled_high = rel_high[perm_intra]
    shuffled_low = rel_low[perm_intra]
    shuffled_close = rel_close[perm_intra]

    # Permute interbar gaps
    perm_gap = rng.permutation(idx)
    shuffled_gap = rel_gap[perm_gap]

    # 4. Vectorized cumulative reconstruction:
    # C_t = C_0 + cumsum(shuffled_gap + shuffled_close)
    bar_returns = shuffled_gap + shuffled_close
    cum_returns = np.cumsum(bar_returns)

    start_log_close = log_close[0]
    out_close = np.empty(n_bars, dtype=np.float64)
    out_open = np.empty(n_bars, dtype=np.float64)
    out_high = np.empty(n_bars, dtype=np.float64)
    out_low = np.empty(n_bars, dtype=np.float64)

    # Start bar remains unchanged
    out_open[0] = log_open[0]
    out_high[0] = log_high[0]
    out_low[0] = log_low[0]
    out_close[0] = start_log_close

    # Reconstructed close and open
    out_close[1:] = start_log_close + cum_returns
    out_open[1:] = np.concatenate(([start_log_close], out_close[1:-1])) + shuffled_gap
    out_high[1:] = out_open[1:] + shuffled_high
    out_low[1:] = out_open[1:] + shuffled_low

    # Convert back from log scale
    exp_open = np.exp(out_open)
    exp_high = np.exp(out_high)
    exp_low = np.exp(out_low)
    exp_close = np.exp(out_close)

    # Ensure validity: high >= max(open, close), low <= min(open, close)
    exp_high = np.maximum(exp_high, np.maximum(exp_open, exp_close))
    exp_low = np.minimum(exp_low, np.minimum(exp_open, exp_close))

    out_df = bars.copy()
    out_df["open"] = exp_open
    out_df["high"] = exp_high
    out_df["low"] = exp_low
    out_df["close"] = exp_close
    return out_df


@dataclass(frozen=True)
class MCPTResult:
    symbol: Symbol
    real_pf: float
    permuted_pfs: list[float]
    p_value: float
    passed: bool
    n_permutations: int


def calculate_mcpt(
    symbol: Symbol,
    bars: pd.DataFrame,
    start: datetime,
    end: datetime,
    real_pf: float,
    n_permutations: int = 20,
    seed: int = 42,
    starting_equity: Decimal = Decimal("10000"),
) -> MCPTResult:
    """Run Monte Carlo Permutation Test by generating synthetic market histories,
    re-running the ICT structure and event loop, and computing the empirical p-value.
    """
    permuted_pfs: list[float] = []
    better_or_equal = 0

    for i in range(n_permutations):
        perm_seed = seed + i * 1000 + 1
        perm_bars = permute_bars(bars, seed=perm_seed)
        pre = precompute(perm_bars, symbol)
        loop = EventLoop(
            symbol,
            [SilverBullet(), JudasSwing()],
            DefaultRiskEngine(),
            pre,
        )
        trades, _ = loop.run(start, end, starting_equity)
        pnls = [t.pnl for t in trades if t.pnl is not None]
        pf = profit_factor(pnls) if len(pnls) > 0 else 0.0
        permuted_pfs.append(pf)
        if pf >= real_pf:
            better_or_equal += 1

    p_val = (1.0 + better_or_equal) / (float(n_permutations) + 1.0)
    passed = p_val < 0.05

    return MCPTResult(
        symbol=symbol,
        real_pf=real_pf,
        permuted_pfs=permuted_pfs,
        p_value=p_val,
        passed=passed,
        n_permutations=n_permutations,
    )
