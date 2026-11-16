"""Cycle 8 scheme-1 MCPT on WTI Tier 1' survivors.

Null: block-bootstrap of daily log-returns (block_size=10), rebuild synthetic
price series, re-run Donchian with the same (lb_e, lb_x, direction) params,
record mean_r. 500 permutations per config.

Statistic: observed mean_r per trade.
p-value: fraction of null mean_r >= observed.

Bonferroni context: per-slot alpha across 36 pre-reg grid slots = 0.0014.

Writes:
  out/c8/mcpt_wti.csv  - per-config observed stats + p + Bonferroni result.
  out/c8/mcpt_wti.log
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_c8_donchian_grid import _load_d1, _simulate, _metrics  # type: ignore

SYMBOL = "LIGHTCMDUSD"
DEV_START = "2015-01-01"
DEV_END = "2023-12-31"
N_PERMS = 500
BLOCK_SIZE = 10
SEED = 20261116
BONFERRONI_ALPHA = 0.05 / 36

SURVIVORS = [
    (55, 10, "long_only"),
    (40, 10, "long_only"),
    (40, 20, "long_only"),
    (55, 20, "long_only"),
    (20, 10, "long_only"),
    (55, 10, "both"),
]

OUT_DIR = Path("out/c8")


def _block_bootstrap_returns(logr: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    n = len(logr)
    n_blocks = (n + BLOCK_SIZE - 1) // BLOCK_SIZE
    starts = rng.integers(0, max(1, n - BLOCK_SIZE + 1), size=n_blocks)
    out = np.empty(n_blocks * BLOCK_SIZE, dtype=logr.dtype)
    for k, s in enumerate(starts):
        out[k * BLOCK_SIZE:(k + 1) * BLOCK_SIZE] = logr[s:s + BLOCK_SIZE]
    return out[:n]


def _synth_d1(d1_obs: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Rebuild a synthetic D1 by bootstrapping mid-close log-returns.

    Shifts bid/ask/high/low around the synthesized mid_c to preserve the
    bar's internal geometry (ranges and spreads) while scrambling the macro
    path. ATR and OHLC consistency are preserved per-bar.
    """
    mid_c = d1_obs["mid_c"].to_numpy(dtype=float)
    logr = np.diff(np.log(mid_c))
    perm = _block_bootstrap_returns(logr, rng)
    # Rebuild mid_c starting from the first observed value.
    new_mid_c = np.empty_like(mid_c)
    new_mid_c[0] = mid_c[0]
    new_mid_c[1:] = mid_c[0] * np.exp(np.cumsum(perm[:len(mid_c) - 1]))
    df = d1_obs.copy()
    delta = new_mid_c - mid_c
    for col in ("mid_c", "mid_h", "mid_l", "bid_o", "bid_h", "bid_l", "bid_c",
                "ask_o", "ask_h", "ask_l", "ask_c"):
        df[col] = d1_obs[col].to_numpy(dtype=float) + delta
    # Recompute ATR20_prev on synthetic path.
    tr = pd.concat([
        (df["mid_h"] - df["mid_l"]).abs(),
        (df["mid_h"] - df["mid_c"].shift(1)).abs(),
        (df["mid_l"] - df["mid_c"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr20_prev"] = tr.rolling(20).mean().shift(1)
    return df


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUT_DIR / "mcpt_wti.log"
    csv_path = OUT_DIR / "mcpt_wti.csv"
    log_path.write_text("", encoding="utf-8")

    def log(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    log(f"START MCPT {SYMBOL} dev {DEV_START}..{DEV_END} perms={N_PERMS} block={BLOCK_SIZE} seed={SEED}")
    d1_full = _load_d1(SYMBOL)
    d1 = d1_full[(d1_full["utc_date"] >= DEV_START) & (d1_full["utc_date"] <= DEV_END)].reset_index(drop=True)
    log(f"loaded {len(d1)} D1 UTC-days")

    rng = np.random.default_rng(SEED)
    rows = []
    for (lb_e, lb_x, dr) in SURVIVORS:
        t0 = time.time()
        trades_obs = _simulate(d1, lb_e, lb_x, dr)
        m_obs = _metrics(trades_obs)
        obs_mean_r = m_obs["mean_r"]

        null_mean_r = np.empty(N_PERMS, dtype=float)
        for p in range(N_PERMS):
            d1_synth = _synth_d1(d1, rng)
            trades_null = _simulate(d1_synth, lb_e, lb_x, dr)
            m_null = _metrics(trades_null)
            null_mean_r[p] = m_null["mean_r"]
        p_val = float((null_mean_r >= obs_mean_r).sum() + 1) / (N_PERMS + 1)
        passed_bonf = p_val <= BONFERRONI_ALPHA
        rows.append({
            "lookback_entry": lb_e,
            "lookback_exit": lb_x,
            "direction": dr,
            "n_trades_obs": m_obs["trades"],
            "pf_obs": m_obs["pf"],
            "mean_r_obs": obs_mean_r,
            "sharpe_obs": m_obs["sharpe"],
            "max_dd_r_obs": m_obs["max_dd_r"],
            "null_mean_r_mean": float(null_mean_r.mean()),
            "null_mean_r_q95": float(np.quantile(null_mean_r, 0.95)),
            "null_mean_r_q99": float(np.quantile(null_mean_r, 0.99)),
            "p_value": p_val,
            "bonferroni_alpha": BONFERRONI_ALPHA,
            "passed_bonferroni": passed_bonf,
        })
        log(f"le={lb_e} lx={lb_x} dr={dr:10s} n={m_obs['trades']:3d} obs_mean_r={obs_mean_r:+.4f} null_mean={null_mean_r.mean():+.4f} q95={np.quantile(null_mean_r,0.95):+.4f} p={p_val:.4f} bonf_pass={passed_bonf} took={time.time()-t0:.1f}s")

    out = pd.DataFrame(rows)
    out.to_csv(csv_path, index=False)
    log(f"wrote {csv_path}")
    log("END MCPT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
