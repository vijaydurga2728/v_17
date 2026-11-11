import numpy as np
from v17.validation.mcpt import block_bootstrap_pnl


def test_block_bootstrap_same_length():
    pnls = np.array([1, -0.5, 1, -0.5, 1, -0.5, 1, -0.5, 1, -0.5])
    out = block_bootstrap_pnl(pnls, block_size=5, seed=42)
    assert len(out) == len(pnls)


def test_deterministic_with_seed():
    pnls = np.array([1, -0.5, 1, -0.5, 1, -0.5])
    a = block_bootstrap_pnl(pnls, block_size=3, seed=7)
    b = block_bootstrap_pnl(pnls, block_size=3, seed=7)
    assert (a == b).all()


def test_different_seed_different_output():
    pnls = np.array([1.0, -0.5, 1.0, -0.5, 1.0, -0.5, 1.0, -0.5])
    a = block_bootstrap_pnl(pnls, block_size=3, seed=7)
    b = block_bootstrap_pnl(pnls, block_size=3, seed=8)
    assert not (a == b).all()


def test_empty_pnls_returns_empty():
    out = block_bootstrap_pnl(np.array([], dtype=float), block_size=5, seed=1)
    assert len(out) == 0
