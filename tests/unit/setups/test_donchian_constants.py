"""Freeze tests for Donchian constants (cycle 4B D1 rewrite)."""
from __future__ import annotations

from v17.setups import donchian_constants as c


def test_channel_lengths_d1():
    assert c.ENTRY_CHANNEL_D1 == 20
    assert c.TRAIL_CHANNEL_D1 == 10


def test_atr_based_stop():
    assert c.ATR_PERIOD_D1 == 20
    assert c.SL_ATR_MULT == 2.0


def test_no_target_r():
    assert not hasattr(c, "TARGET_R")


def test_cost_model_has_usatech_and_fx_pip():
    assert "USATECHIDXUSD" in c.COST_SLIPPAGE_PTS
    assert c.COST_SLIPPAGE_PIPS_FX == 0.5
