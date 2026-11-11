"""Freeze tests for TSM engine catalog."""
from __future__ import annotations

import dataclasses

from v17.setups.tsm_engines import TSM_CATALOG, TSMEngineConfig


def test_catalog_has_three_engines():
    assert len(TSM_CATALOG) == 3
    ids = {e.engine_id for e in TSM_CATALOG}
    assert ids == {"TSM-EURUSD", "TSM-GBPUSD", "TSM-USATECHIDXUSD"}


def test_catalog_covers_three_instruments():
    syms = {e.symbol for e in TSM_CATALOG}
    assert syms == {"EURUSD", "GBPUSD", "USATECHIDXUSD"}


def test_engine_config_is_frozen():
    e = TSM_CATALOG[0]
    try:
        e.priority_order = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("TSMEngineConfig should be frozen")
