from v17.setups.sb_engines import ENGINE_CATALOG, SBEngineConfig


def test_six_engines_defined():
    assert len(ENGINE_CATALOG) == 6
    ids = [e.engine_id for e in ENGINE_CATALOG]
    assert ids == [
        "SB-LDN-CE", "SB-LDN-AG",
        "SB-NYAM-CE", "SB-NYAM-AG",
        "SB-NYPM-CE", "SB-NYPM-AG",
    ]


def test_eligible_symbols_per_window():
    cat = {e.engine_id: e for e in ENGINE_CATALOG}
    assert set(cat["SB-LDN-CE"].symbols) == {"EURUSD", "GBPUSD"}
    assert set(cat["SB-NYAM-CE"].symbols) == {"USATECHIDXUSD", "EURUSD", "GBPUSD"}
    assert set(cat["SB-NYPM-CE"].symbols) == {"USATECHIDXUSD"}


def test_entry_models():
    cat = {e.engine_id: e for e in ENGINE_CATALOG}
    assert cat["SB-LDN-CE"].entry_model == "CE"
    assert cat["SB-LDN-AG"].entry_model == "AGGRESSIVE"


def test_window_times_ny():
    cat = {e.engine_id: e for e in ENGINE_CATALOG}
    assert cat["SB-LDN-CE"].window_ny == ("03:00", "04:00")
    assert cat["SB-NYAM-CE"].window_ny == ("10:00", "11:00")
    assert cat["SB-NYPM-CE"].window_ny == ("14:00", "15:00")


def test_priority_order_ascending():
    orders = [e.priority_order for e in ENGINE_CATALOG]
    assert orders == [1, 2, 3, 4, 5, 6]
