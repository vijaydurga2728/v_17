import numpy as np
import pandas as pd

from v17.validation.c6_mcpt import scheme1_mcpt


def _tl(pnls):
    return pd.DataFrame({
        "entry_ts_ns": [i * 1_000_000_000 for i in range(len(pnls))],
        "net_pnl_usd": pnls, "equity_sod": [10_000] * len(pnls),
    })


def test_scheme1_observed_beats_random_null():
    obs = _tl([50, 60, 40, 70, -20] * 20)  # strong positive drift

    def run_null(perm_idx):
        rng = np.random.default_rng(perm_idx + 7)
        return _tl(rng.normal(0, 40, 100).tolist())

    r = scheme1_mcpt(obs, run_null, n_permutations=50, seed=42)
    assert r["p_sharpe"] <= 0.10  # observed should beat random null most of the time


def test_scheme1_observed_indistinguishable_from_null():
    rng = np.random.default_rng(3)
    obs = _tl(rng.normal(0, 40, 100).tolist())

    def run_null(perm_idx):
        rng2 = np.random.default_rng(perm_idx + 1000)
        return _tl(rng2.normal(0, 40, 100).tolist())

    r = scheme1_mcpt(obs, run_null, n_permutations=50, seed=42)
    assert 0.05 <= r["p_sharpe"] <= 0.95
