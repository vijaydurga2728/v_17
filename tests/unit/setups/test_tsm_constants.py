"""Freeze tests for TSM constants."""
from __future__ import annotations

from v17.setups import tsm_constants as c


def test_lookback_and_hold_in_h1():
    assert c.LOOKBACK_H1 == 480
    assert c.HOLD_H1 == 120


def test_sl_and_target():
    assert c.ATR_PERIOD_H1 == 14
    assert c.SL_ATR_MULT == 2.0
    assert c.TARGET_R == 3.0


def test_cost_model_present_for_all_symbols():
    assert "USATECHIDXUSD" in c.COST_SLIPPAGE_PTS
    assert c.COST_SLIPPAGE_PIPS_FX == 0.5
