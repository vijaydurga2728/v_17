from v17.setups.c6_engines import C6_CATALOG, C6EngineConfig


def test_catalog_two_pairs():
    assert len(C6_CATALOG) == 2
    ids = {c.engine_id for c in C6_CATALOG}
    assert ids == {"C6-AUDUSD", "C6-USDJPY"}


def test_catalog_pip_sizes():
    by_sym = {c.symbol: c for c in C6_CATALOG}
    assert by_sym["AUDUSD"].pip_size == 0.0001
    assert by_sym["USDJPY"].pip_size == 0.01


def test_catalog_pip_value_callables():
    by_sym = {c.symbol: c for c in C6_CATALOG}
    assert by_sym["AUDUSD"].pip_value_per_lot(0.65) == 10.0
    assert abs(by_sym["USDJPY"].pip_value_per_lot(150.0) - 6.6666666666) < 1e-6


def test_catalog_priority_order_distinct():
    orders = [c.priority_order for c in C6_CATALOG]
    assert len(set(orders)) == len(orders)
