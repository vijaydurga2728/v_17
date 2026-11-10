"""Unit tests for _simulate_fill (Phase C) and _commission (Phase D)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from v17.backtest.engine_runner import (
    _simulate_fill,
    _commission_round_turn,
    _RISK_PER_TRADE,
    _COMMISSION_FX_RT,
    _COMMISSION_IDX_RT,
)
from v17.setups.silver_bullet_fsm import SBSignal


def _make_signal(
    side: str,
    entry: float,
    sl: float,
    tp: float,
    r_multiple: float = 2.0,
    symbol: str = "EURUSD",
    ts_entry_ns: int = 1_000_000_000,
) -> SBSignal:
    return SBSignal(
        engine_id="SB-TEST",
        symbol=symbol,
        side=side,
        ts_entry_ns=ts_entry_ns,
        entry_price=entry,
        sl_price=sl,
        tp_price=tp,
        r_multiple=r_multiple,
        fvg_top=entry + 0.001,
        fvg_bottom=entry,
    )


def _make_bars(
    ts_list: list[int],
    bid_h: list[float],
    bid_l: list[float],
    bid_c: list[float],
    spread: float = 0.0001,
    symbol: str = "EURUSD",
) -> pd.DataFrame:
    n = len(ts_list)
    ask_c = [b + spread for b in bid_c]
    return pd.DataFrame({
        "ts_utc": ts_list,
        "symbol": [symbol] * n,
        "bid_h": bid_h,
        "bid_l": bid_l,
        "bid_c": bid_c,
        "ask_c": ask_c,
        "spread_mid": [spread] * n,
    })


_MIN_NS = 60_000_000_000


# ---------------------------------------------------------------------------
# Commission tests
# ---------------------------------------------------------------------------

def test_commission_fx():
    assert _commission_round_turn("EURUSD") == _COMMISSION_FX_RT
    assert _commission_round_turn("GBPUSD") == _COMMISSION_FX_RT


def test_commission_index():
    assert _commission_round_turn("USATECHIDXUSD") == _COMMISSION_IDX_RT


# ---------------------------------------------------------------------------
# LONG scenarios
# ---------------------------------------------------------------------------

def test_long_hits_tp():
    # Entry 1.1000, SL 1.0990, TP 1.1020, r_multiple=2.0
    sig = _make_signal("LONG", entry=1.1000, sl=1.0990, tp=1.1020, r_multiple=2.0)
    bars = _make_bars(
        ts_list=[sig.ts_entry_ns, sig.ts_entry_ns + _MIN_NS],
        bid_h=[1.1000, 1.1025],  # second bar: bid_h >= tp
        bid_l=[1.0995, 1.1010],
        bid_c=[1.1000, 1.1020],
    )
    result = _simulate_fill(sig, bars, hard_exit_ns=sig.ts_entry_ns + 10 * _MIN_NS)
    assert result["exit_reason"] == "TP"
    assert abs(result["exit_price"] - 1.1020) < 1e-9
    assert abs(result["pnl_r"] - 2.0) < 1e-9


def test_long_hits_sl():
    sig = _make_signal("LONG", entry=1.1000, sl=1.0990, tp=1.1020, r_multiple=2.0)
    bars = _make_bars(
        ts_list=[sig.ts_entry_ns, sig.ts_entry_ns + _MIN_NS],
        bid_h=[1.1000, 1.1005],
        bid_l=[1.0995, 1.0988],  # second bar: bid_l <= sl
        bid_c=[1.1000, 1.0990],
    )
    result = _simulate_fill(sig, bars, hard_exit_ns=sig.ts_entry_ns + 10 * _MIN_NS)
    assert result["exit_reason"] == "SL"
    assert abs(result["exit_price"] - 1.0990) < 1e-9
    assert abs(result["pnl_r"] - (-1.0)) < 1e-9


def test_long_time_exit():
    sig = _make_signal("LONG", entry=1.1000, sl=1.0990, tp=1.1020, r_multiple=2.0)
    # Neither SL nor TP touched; exits at hard_exit_ns bar.
    exit_price = 1.1005
    bars = _make_bars(
        ts_list=[sig.ts_entry_ns, sig.ts_entry_ns + _MIN_NS, sig.ts_entry_ns + 2 * _MIN_NS],
        bid_h=[1.1002, 1.1003, 1.1010],   # never reaches tp=1.1020
        bid_l=[1.0995, 1.0996, 1.0996],   # never hits sl=1.0990
        bid_c=[1.1001, 1.1002, exit_price],
    )
    hard_exit_ns = sig.ts_entry_ns + 2 * _MIN_NS
    result = _simulate_fill(sig, bars, hard_exit_ns=hard_exit_ns)
    assert result["exit_reason"] == "TIME"
    assert abs(result["exit_price"] - exit_price) < 1e-9
    # pnl_r = (exit - entry) / risk_dist = (1.1005 - 1.1000) / (1.1000 - 1.0990) = 0.5
    assert abs(result["pnl_r"] - 0.5) < 1e-6


def test_long_sl_wins_when_both_in_same_bar():
    # Both SL and TP touched in same bar → SL wins (worst case).
    sig = _make_signal("LONG", entry=1.1000, sl=1.0990, tp=1.1020, r_multiple=2.0)
    bars = _make_bars(
        ts_list=[sig.ts_entry_ns],
        bid_h=[1.1025],   # >= tp=1.1020
        bid_l=[1.0985],   # <= sl=1.0990
        bid_c=[1.1000],
    )
    result = _simulate_fill(sig, bars, hard_exit_ns=sig.ts_entry_ns + 10 * _MIN_NS)
    assert result["exit_reason"] == "SL"
    assert abs(result["pnl_r"] - (-1.0)) < 1e-9


# ---------------------------------------------------------------------------
# SHORT scenarios
# ---------------------------------------------------------------------------

def test_short_hits_tp():
    # Entry 1.1000, SL 1.1010, TP 1.0980, r_multiple=2.0
    sig = _make_signal("SHORT", entry=1.1000, sl=1.1010, tp=1.0980, r_multiple=2.0)
    bars = _make_bars(
        ts_list=[sig.ts_entry_ns, sig.ts_entry_ns + _MIN_NS],
        bid_h=[1.1002, 1.0990],
        bid_l=[1.0995, 1.0975],  # bid_l <= tp=1.0980
        bid_c=[1.1000, 1.0982],
    )
    result = _simulate_fill(sig, bars, hard_exit_ns=sig.ts_entry_ns + 10 * _MIN_NS)
    assert result["exit_reason"] == "TP"
    assert abs(result["exit_price"] - 1.0980) < 1e-9
    assert abs(result["pnl_r"] - 2.0) < 1e-9


def test_short_hits_sl():
    sig = _make_signal("SHORT", entry=1.1000, sl=1.1010, tp=1.0980, r_multiple=2.0)
    bars = _make_bars(
        ts_list=[sig.ts_entry_ns, sig.ts_entry_ns + _MIN_NS],
        bid_h=[1.1002, 1.1012],  # bid_h >= sl=1.1010
        bid_l=[1.0995, 1.0998],
        bid_c=[1.1000, 1.1005],
    )
    result = _simulate_fill(sig, bars, hard_exit_ns=sig.ts_entry_ns + 10 * _MIN_NS)
    assert result["exit_reason"] == "SL"
    assert abs(result["exit_price"] - 1.1010) < 1e-9
    assert abs(result["pnl_r"] - (-1.0)) < 1e-9


def test_short_time_exit():
    sig = _make_signal("SHORT", entry=1.1000, sl=1.1010, tp=1.0980, r_multiple=2.0)
    spread = 0.0001
    exit_bid_c = 1.0998
    exit_ask_c = exit_bid_c + spread
    bars = _make_bars(
        ts_list=[sig.ts_entry_ns, sig.ts_entry_ns + _MIN_NS],
        bid_h=[1.1002, 1.1003],  # never >= sl
        bid_l=[1.0995, 1.0995],  # never <= tp
        bid_c=[1.1000, exit_bid_c],
        spread=spread,
    )
    hard_exit_ns = sig.ts_entry_ns + _MIN_NS
    result = _simulate_fill(sig, bars, hard_exit_ns=hard_exit_ns)
    assert result["exit_reason"] == "TIME"
    assert abs(result["exit_price"] - exit_ask_c) < 1e-9
    # pnl_r = (entry - exit_ask_c) / (sl - entry) = (1.1000 - 1.0999) / (1.1010 - 1.1000) = 0.1
    expected_pnl_r = (1.1000 - exit_ask_c) / (1.1010 - 1.1000)
    assert abs(result["pnl_r"] - expected_pnl_r) < 1e-6


def test_short_sl_wins_when_both_in_same_bar():
    sig = _make_signal("SHORT", entry=1.1000, sl=1.1010, tp=1.0980, r_multiple=2.0)
    bars = _make_bars(
        ts_list=[sig.ts_entry_ns],
        bid_h=[1.1015],   # >= sl=1.1010
        bid_l=[1.0975],   # <= tp=1.0980
        bid_c=[1.1000],
    )
    result = _simulate_fill(sig, bars, hard_exit_ns=sig.ts_entry_ns + 10 * _MIN_NS)
    assert result["exit_reason"] == "SL"
    assert abs(result["pnl_r"] - (-1.0)) < 1e-9
