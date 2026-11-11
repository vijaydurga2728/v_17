"""ORB engine catalog freeze tests."""
from __future__ import annotations

from v17.setups.orb_engines import ORB_CATALOG, ORBEngineConfig


def test_catalog_has_one_engine() -> None:
    assert len(ORB_CATALOG) == 1
    ids = {e.engine_id for e in ORB_CATALOG}
    assert ids == {"ORB-NAS100"}


def test_engine_windows_match_spec() -> None:
    for e in ORB_CATALOG:
        assert e.or_window_ny == ("09:30", "10:00")
        assert e.session_window_ny == ("09:30", "11:30")


def test_engine_config_is_frozen() -> None:
    import dataclasses
    assert any(f.name == "engine_id" for f in dataclasses.fields(ORBEngineConfig))
    # Frozen dataclass — mutation must raise.
    e = ORB_CATALOG[0]
    try:
        e.priority_order = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("ORBEngineConfig should be frozen")


def test_nas100_symbol() -> None:
    assert ORB_CATALOG[0].symbol == "USATECHIDXUSD"
