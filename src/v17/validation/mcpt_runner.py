"""MCPT runner — dual-scheme permutation harness (spec section 7)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from v17.validation.mcpt import block_bootstrap_pnl, permute_signal_time
from v17.validation.seeds import permutation_seed
from v17.validation.stats import compute_stats


_BLOCK_SIZE = 5  # one trading week


def run_mcpt(
    engine_id: str,
    trades: pd.DataFrame,
    bars: pd.DataFrame,
    calendar: pd.DataFrame,
    scheme: str,
    n_permutations: int,
    out_root: Path,
) -> dict:
    pnls = trades["pnl_r"].to_numpy()
    ts = trades["ts_entry_ns"].to_numpy()
    observed = compute_stats(pnls, ts)

    rows: list[dict] = []
    for i in range(n_permutations):
        seed = permutation_seed(engine_id, scheme, i)
        if scheme == "signal_time":
            permuted_trades = permute_signal_time(trades, bars, config=None, seed=seed)
            s = compute_stats(
                permuted_trades["pnl_r"].to_numpy(),
                permuted_trades["ts_entry_ns"].to_numpy(),
            )
        elif scheme == "pnl_bootstrap":
            permuted = block_bootstrap_pnl(pnls, block_size=_BLOCK_SIZE, seed=seed)
            s = compute_stats(permuted, ts)
        else:
            raise ValueError(f"Unknown scheme: {scheme!r}")
        rows.append({
            "perm_idx": i,
            "sharpe": s.sharpe,
            "pf": s.pf if np.isfinite(s.pf) else float("nan"),
            "max_dd": s.max_dd,
            "r2": s.r2,
            "trade_count": s.trade_count,
        })

    df = pd.DataFrame(rows)
    out = Path(out_root) / "mcpt" / engine_id / scheme / "permutations.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)

    p_sharpe = float((df["sharpe"] >= observed.sharpe).mean())
    # Filter out non-finite PF before comparison
    finite_pf = df["pf"].dropna()
    if np.isfinite(observed.pf) and len(finite_pf) > 0:
        p_pf = float((finite_pf >= observed.pf).mean())
    else:
        p_pf = float("nan")

    return {
        "engine_id": engine_id,
        "scheme": scheme,
        "observed_sharpe": observed.sharpe,
        "observed_pf": observed.pf,
        "p_sharpe": p_sharpe,
        "p_pf": p_pf,
        "n_permutations": n_permutations,
    }
