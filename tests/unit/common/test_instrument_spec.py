from v17.common.instrument_spec import pip_size


def test_fx_majors_1e_minus_4():
    assert pip_size("EURUSD") == 0.0001
    assert pip_size("GBPUSD") == 0.0001


def test_usdjpy_1e_minus_2():
    assert pip_size("USDJPY") == 0.01


def test_indices_1():
    assert pip_size("USATECHIDXUSD") == 1.0
    assert pip_size("USA500IDXUSD") == 1.0


def test_default_fallback_fx():
    assert pip_size("UNKNOWNFX") == 0.0001
