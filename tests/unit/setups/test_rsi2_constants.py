"""Freeze tests for RSI(2) constants (cycle 4B D1 long-only)."""
from __future__ import annotations

from v17.setups import rsi2_constants as c


def test_rsi_period_and_long_threshold():
    assert c.RSI_PERIOD_D1 == 2
    assert c.LONG_THRESHOLD == 10.0


def test_sma_exit_and_time_cap():
    assert c.SMA_EXIT_PERIOD_D1 == 5
    assert c.TIME_CAP_D1 == 10


def test_long_only_no_short_threshold():
    assert not hasattr(c, "SHORT_THRESHOLD")  # cycle 4B: long-only
    assert not hasattr(c, "EXIT_MID")         # replaced by SMA exit


def test_no_stop_loss():
    assert not hasattr(c, "SL_ATR_MULT")      # Connors spec: no SL
    assert not hasattr(c, "ATR_PERIOD_H1")
    assert not hasattr(c, "ATR_PERIOD_D1")


def test_usatech_slippage():
    assert c.COST_SLIPPAGE_PTS_USATECH == 0.5
