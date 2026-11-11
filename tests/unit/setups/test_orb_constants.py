"""Freeze-tests for ORB constants. Any value drift is a spec amendment."""
from __future__ import annotations

from v17.setups import orb_constants as c


def test_breakers_match_spec() -> None:
    assert c.DAILY_LOSS_SOFT_STOP == 0.03
    assert c.TOTAL_LOSS_HARD_FREEZE == 0.08


def test_or_window_30min() -> None:
    assert c.OR_WINDOW_NY == ("09:30", "10:00")
    assert c.OR_DURATION_MIN == 30


def test_session_window_two_hours() -> None:
    assert c.SESSION_WINDOW_NY == ("09:30", "11:30")


def test_reversal_confirm_window() -> None:
    assert c.REVERSAL_CONFIRM_MAX_MIN == 15


def test_sl_atr_mult() -> None:
    assert c.ATR_PERIOD_M1 == 14
    assert c.SL_ATR_MULT == 0.5


def test_target_half_r() -> None:
    assert c.TARGET_R == 0.5


def test_trade_cap() -> None:
    assert c.MAX_TRADES_PER_DAY_PER_INSTRUMENT == 1


def test_cost_ftmo_zero_commission_on_indices() -> None:
    assert c.COMMISSION_PER_LOT["USATECHIDXUSD"] == 0.0


def test_cost_slippage_defined_for_nas100() -> None:
    assert c.COST_SLIPPAGE_PTS["USATECHIDXUSD"] == 0.5
