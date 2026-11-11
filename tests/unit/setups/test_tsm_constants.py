"""Freeze tests for TSM constants (cycle 4B D1 rewrite)."""
from __future__ import annotations

from v17.setups import tsm_constants as c


def test_lookback_and_hold_in_d1():
    assert c.LOOKBACK_D1 == 252
    assert c.HOLD_D1 == 21


def test_sl_no_target():
    assert c.ATR_PERIOD_D1 == 14
    assert c.SL_ATR_MULT == 2.0
    assert not hasattr(c, "TARGET_R")  # cycle 4B: hard target removed


def test_cost_model_present_for_all_symbols():
    assert "USATECHIDXUSD" in c.COST_SLIPPAGE_PTS
    assert c.COST_SLIPPAGE_PIPS_FX == 0.5
