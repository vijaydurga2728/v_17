from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
import pytest

from v17.setups.c9_pdh_pdl import PRICE_FIELDS, Sessions

Bar = tuple[float, float, float, float]  # mid o, h, l, c


def make_sessions(days: Sequence[Sequence[Bar]], spread: float = 0.0,
                  prev_ok: Sequence[bool] | None = None, final_bin: bool = True) -> Sessions:
    """Hand-built Sessions: bid = mid - spread/2, ask = mid + spread/2.

    Bars get bins 0, 1, 2, ...; with ``final_bin`` the LAST bar of each session is
    labelled bin 24 ([15:30, 15:45)) so the session is entry-eligible (IMPL-8).
    """
    rows = [bar for day in days for bar in day]
    arr = np.asarray(rows, dtype=np.float64).reshape(-1, 4)
    half = spread / 2.0
    prices: dict[str, np.ndarray] = {}
    for i, s in enumerate("ohlc"):
        prices[f"mid_{s}"] = arr[:, i].copy()
        prices[f"bid_{s}"] = arr[:, i] - half
        prices[f"ask_{s}"] = arr[:, i] + half
    assert set(prices) == set(PRICE_FIELDS)
    lens = [len(d) for d in days]
    offsets = np.r_[0, np.cumsum(lens)].astype(np.int64)
    bins = np.concatenate([np.arange(n) for n in lens]).astype(np.int64)
    if final_bin:
        bins[offsets[1:] - 1] = 24
    dates = (np.datetime64("2020-01-06") + np.arange(len(days))).astype("datetime64[D]")
    ok = np.r_[False, np.ones(len(days) - 1, bool)] if prev_ok is None else np.asarray(prev_ok, bool)
    return Sessions(dates, offsets, bins, prices, ok)


@pytest.fixture
def mk() -> Callable[..., Sessions]:
    return make_sessions
