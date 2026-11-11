"""Freeze tests for RSI(2) engine catalog."""
from __future__ import annotations

import dataclasses

from v17.setups.rsi2_engines import RSI2_CATALOG, RSI2EngineConfig


def test_catalog_has_two_fx_engines():
    assert len(RSI2_CATALOG) == 2
    ids = {e.engine_id for e in RSI2_CATALOG}
    assert ids == {"RSI2-EURUSD", "RSI2-GBPUSD"}


def test_catalog_excludes_index():
    syms = {e.symbol for e in RSI2_CATALOG}
    assert "USATECHIDXUSD" not in syms


def test_engine_config_is_frozen():
    e = RSI2_CATALOG[0]
    try:
        e.priority_order = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("RSI2EngineConfig should be frozen")
