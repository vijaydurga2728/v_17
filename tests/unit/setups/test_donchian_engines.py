"""Freeze tests for Donchian engine catalog."""
from __future__ import annotations

import dataclasses

from v17.setups.donchian_engines import DONCHIAN_CATALOG, DonchianEngineConfig


def test_catalog_has_three_engines():
    assert len(DONCHIAN_CATALOG) == 3
    ids = {e.engine_id for e in DONCHIAN_CATALOG}
    assert ids == {"DON-EURUSD", "DON-GBPUSD", "DON-USATECHIDXUSD"}


def test_catalog_covers_three_instruments():
    syms = {e.symbol for e in DONCHIAN_CATALOG}
    assert syms == {"EURUSD", "GBPUSD", "USATECHIDXUSD"}


def test_engine_config_is_frozen():
    e = DONCHIAN_CATALOG[0]
    try:
        e.priority_order = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("DonchianEngineConfig should be frozen")
