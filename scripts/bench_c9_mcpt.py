"""Benchmark one cycle 9 MCPT permutation: numba vs pure Python.

Uses SYNTHETIC random-walk sessions shaped like dev (2,000 sessions x 25 bins).
Reads no market data and produces no strategy performance numbers.

Usage: .venv/Scripts/python.exe scripts/bench_c9_mcpt.py [n_perms]
"""
from __future__ import annotations

import platform
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from v17.setups import c9_pdh_pdl as c9
from v17.validation.c9_mcpt import N_PERMS, SessionPool, mean_r_of


def synthetic_dev(n_sessions: int = 2000, seed: int = 0) -> c9.Sessions:
    rng = np.random.default_rng(seed)
    n = n_sessions * c9.N_TRADABLE_BINS
    mid_c = 4000 + np.cumsum(rng.normal(0, 8, n))
    mid_o = mid_c + rng.normal(0, 1, n)
    mid_h = np.maximum(mid_o, mid_c) + 5 + rng.random(n)
    mid_l = np.minimum(mid_o, mid_c) - 5 - rng.random(n)
    prices = {}
    for k, v in zip("ohlc", (mid_o, mid_h, mid_l, mid_c), strict=True):
        prices[f"mid_{k}"] = v
        prices[f"bid_{k}"] = v - 0.5
        prices[f"ask_{k}"] = v + 0.5
    offsets = np.arange(0, n + 1, c9.N_TRADABLE_BINS, dtype=np.int64)
    bins = np.tile(np.arange(c9.N_TRADABLE_BINS), n_sessions).astype(np.int64)
    dates = (np.datetime64("2015-01-02") + np.arange(n_sessions)).astype("datetime64[D]")
    prev_ok = np.r_[False, np.ones(n_sessions - 1, bool)]
    return c9.Sessions(dates, offsets, bins, prices, prev_ok)


def time_perms(sess: c9.Sessions, n: int) -> float:
    pool = SessionPool(sess)
    slot = c9.Slot(0.05, "long_only", 2)
    mean_r_of(sess, slot, 0.0)  # warm-up (jit compile when numba is active)
    t0 = time.perf_counter()
    for j in range(n):
        draw = np.random.default_rng([1, j]).integers(1, sess.n_sessions, size=sess.n_sessions - 1)
        mean_r_of(pool.synthetic(draw), slot, 0.0)
    return (time.perf_counter() - t0) / n


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    sess = synthetic_dev()
    import numba

    print(f"python {platform.python_version()} | numba {numba.__version__} at {numba.__file__}")
    jit_dt = time_perms(sess, n)
    # Pure Python: swap in the un-jitted functions for the same run.
    jit_sim, jit_atr = c9._simulate_core, c9._atr_prev_core
    c9._simulate_core, c9._atr_prev_core = jit_sim.py_func, jit_atr.py_func
    try:
        py_dt = time_perms(sess, max(5, n // 40))
    finally:
        c9._simulate_core, c9._atr_prev_core = jit_sim, jit_atr
    for name, dt in (("numba", jit_dt), ("pure-python", py_dt)):
        hours = dt * N_PERMS / 3600
        print(f"{name:12s} {dt * 1000:9.2f} ms/perm | {N_PERMS:,} perms = {hours:7.2f} h/slot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
