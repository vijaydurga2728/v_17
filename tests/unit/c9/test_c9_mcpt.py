"""Cycle 9 MCPT tests (ADR 002 I, J, K)."""
from __future__ import annotations

import numpy as np
import pytest

from v17.backtest.c9_runner import HoldoutAccessError, load_m1, metrics, tier1_pass
from v17.setups.c9_pdh_pdl import PRICE_FIELDS, Slot
from v17.validation.c9_mcpt import N_PERMS, SessionPool, fixed_count_p, run_mcpt

from .conftest import make_sessions


def _random_sessions(n_days: int = 40, seed: int = 3, spread: float = 0.4):
    rng = np.random.default_rng(seed)
    days = []
    level = 1000.0
    for _ in range(n_days):
        level *= np.exp(rng.normal(0, 0.01))
        n = int(rng.integers(20, 26))  # variable session length (sparse bins)
        c = level + rng.normal(0, 3, n).cumsum()
        days.append([(x + rng.normal(0, 1), x + 2 + rng.random(), x - 2 - rng.random(), x)
                     for x in c])
        level = c[-1]
    s = make_sessions(days, spread=spread)
    s.prices["ask_h"] = s.prices["ask_h"] + rng.random(len(s.bins))  # non-constant geometry
    return s


# ------------------------------------------------- fixed-count p (J rev 2)
def test_fixed_count_p_formula():
    assert fixed_count_p(0, 100_000) == pytest.approx(1 / 100_001)
    assert fixed_count_p(4_999, 100_000) == pytest.approx(5_000 / 100_001)
    assert fixed_count_p(100_000, 100_000) == 1.0
    with pytest.raises(ValueError, match="exceedances"):
        fixed_count_p(5, 4)


def test_min_resolvable_p_below_bonferroni():
    assert fixed_count_p(0, 100_000) < 0.05 / 132


# ---------------------------------------------------------- null path (I)
def test_identity_draw_reproduces_real_path():
    s = _random_sessions()
    syn = SessionPool(s).synthetic(np.arange(1, s.n_sessions))
    np.testing.assert_array_equal(syn.offsets, s.offsets)
    for f in PRICE_FIELDS:
        np.testing.assert_allclose(syn[f], s[f], rtol=1e-12)


def test_synthetic_preserves_session_shape_and_geometry():
    s = _random_sessions()
    pool = SessionPool(s)
    draw = np.random.default_rng(9).integers(1, s.n_sessions, size=s.n_sessions - 1)
    syn = pool.synthetic(draw)
    assert syn.n_sessions == s.n_sessions
    np.testing.assert_array_equal(np.diff(syn.offsets)[1:], pool.lens[draw])
    np.testing.assert_array_equal(syn.dates, s.dates)          # calendar labels stay real
    n0 = pool.n0
    for f in PRICE_FIELDS:                                       # anchor session untouched
        np.testing.assert_array_equal(syn[f][:n0], s[f][:n0])
    # per-bar geometry relative to mid close travels with the source bar
    src = np.concatenate([np.arange(s.offsets[d], s.offsets[d + 1]) for d in draw])
    for f in ("ask_h", "bid_l", "mid_o", "ask_c"):
        np.testing.assert_allclose(syn[f][n0:] - syn["mid_c"][n0:], s[f][src] - s["mid_c"][src],
                                   atol=1e-9)
    # returns: each block's gap + intraday log-returns equal the source session's
    mc, smc = s["mid_c"], syn["mid_c"]
    for t, d in enumerate(draw, start=1):
        a, b = syn.offsets[t], syn.offsets[t + 1]
        sa, sb = s.offsets[d], s.offsets[d + 1]
        assert np.log(smc[a] / smc[a - 1]) == pytest.approx(np.log(mc[sa] / mc[sa - 1]))
        np.testing.assert_allclose(np.diff(np.log(smc[a:b])), np.diff(np.log(mc[sa:sb])), atol=1e-12)


def test_run_mcpt_fixed_count_deterministic_and_logged():
    s = _random_sessions(n_days=30)
    slot = Slot(0.05, "long_only", 2)
    r1, obs1, log1 = run_mcpt(s, slot, n_perms=200)
    r2, obs2, log2 = run_mcpt(s, slot, n_perms=200)
    assert r1 == r2 and obs1 == obs2 and log1.equals(log2)
    assert r1.n_perms == 200 and len(log1) == 200          # never stops early
    assert r1.exceedances == int((log1["mean_r_null"] >= obs1).sum())
    assert r1.p_value == pytest.approx((r1.exceedances + 1) / 201)
    assert set(log1.columns) == {"perm", "seed", "blocks_hash", "n_trades_null", "mean_r_null"}
    assert (log1["seed"] == 20261116005).all()  # slot index 5
    rh, _, logh = run_mcpt(s, slot, n_perms=50, holdout=True)
    assert (logh["seed"] == 20261116505).all() and rh.n_perms == 50   # ADR 002 K seed


def test_default_permutation_count_is_adr001():
    assert N_PERMS == 100_000


# ------------------------------------------------------- runner guards / metrics
def test_holdout_is_sealed():
    with pytest.raises(HoldoutAccessError):
        load_m1("holdout")


def test_metrics_and_tier1():
    r = np.array([2.0, -1.0, -1.0, 3.0, -1.0])
    m = metrics(r)
    assert m["pf"] == pytest.approx(5 / 3)
    assert m["max_dd_r"] == pytest.approx(2.0)
    assert m["n_trades"] == 5
    assert not tier1_pass(m)  # n < 100
    m_many = metrics(np.tile(r, 25))
    assert m_many["n_trades"] == 125 and tier1_pass(m_many)
    bad = metrics(np.tile(np.array([1.0, *[-1.0] * 9, 10.5]), 12))  # 9R drawdown
    assert bad["max_dd_r"] > 8 and not tier1_pass(bad)
