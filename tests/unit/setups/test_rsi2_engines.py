"""Freeze tests for RSI(2) engine catalog (cycle 4B NAS100-only)."""
from __future__ import annotations

import dataclasses

from v17.setups.rsi2_engines import RSI2_CATALOG, RSI2EngineConfig


def test_catalog_has_one_nas100_engine():
    assert len(RSI2_CATALOG) == 1
    assert RSI2_CATALOG[0].engine_id == "RSI2-USATECHIDXUSD"
    assert RSI2_CATALOG[0].symbol == "USATECHIDXUSD"


def test_catalog_excludes_fx():
    syms = {e.symbol for e in RSI2_CATALOG}
    assert "EURUSD" not in syms
    assert "GBPUSD" not in syms


def test_engine_config_is_frozen():
    e = RSI2_CATALOG[0]
    try:
        e.priority_order = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("RSI2EngineConfig should be frozen")
