"""Freeze tests for RSI(2) constants."""
from __future__ import annotations

from v17.setups import rsi2_constants as c


def test_rsi_period_and_thresholds():
    assert c.RSI_PERIOD_H1 == 2
    assert c.LONG_THRESHOLD == 10.0
    assert c.SHORT_THRESHOLD == 90.0
    assert c.EXIT_MID == 50.0


def test_time_cap_and_sl():
    assert c.TIME_CAP_H1 == 5
    assert c.ATR_PERIOD_H1 == 14
    assert c.SL_ATR_MULT == 2.0


def test_fx_slippage_only():
    assert c.COST_SLIPPAGE_PIPS_FX == 0.5
