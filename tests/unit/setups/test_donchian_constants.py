"""Freeze tests for Donchian constants."""
from __future__ import annotations

from v17.setups import donchian_constants as c


def test_channel_lengths():
    assert c.ENTRY_CHANNEL_H1 == 20
    assert c.TRAIL_CHANNEL_H1 == 10


def test_target_r():
    assert c.TARGET_R == 2.0


def test_cost_model_has_usatech_and_fx_pip():
    assert "USATECHIDXUSD" in c.COST_SLIPPAGE_PTS
    assert c.COST_SLIPPAGE_PIPS_FX == 0.5
