import numpy as np
import pandas as pd

from v17.validation.c6_paired_alpha import paired_alpha


def test_paired_alpha_rejects_null_when_obs_much_better():
    obs = pd.DataFrame({"net_pnl_usd": np.random.default_rng(1).normal(10, 30, 500)})
    nul = pd.DataFrame({"net_pnl_usd": np.random.default_rng(2).normal(-5, 30, 500)})
    p = paired_alpha(obs, nul, seed=42, n_bootstrap=500)
    assert p < 0.05


def test_paired_alpha_cant_reject_when_similar():
    rng = np.random.default_rng(1)
    obs = pd.DataFrame({"net_pnl_usd": rng.normal(0, 30, 500)})
    nul = pd.DataFrame({"net_pnl_usd": rng.normal(0, 30, 500)})
    p = paired_alpha(obs, nul, seed=42, n_bootstrap=500)
    assert p > 0.10
