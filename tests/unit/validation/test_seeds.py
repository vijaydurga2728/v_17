from v17.validation.seeds import permutation_seed


def test_seed_is_deterministic():
    assert permutation_seed("SB-LDN-CE", "signal_time", 0) == permutation_seed("SB-LDN-CE", "signal_time", 0)


def test_different_engine_different_seed():
    a = permutation_seed("SB-LDN-CE", "signal_time", 0)
    b = permutation_seed("SB-LDN-AG", "signal_time", 0)
    assert a != b


def test_different_perm_index_different_seed():
    a = permutation_seed("SB-LDN-CE", "signal_time", 0)
    b = permutation_seed("SB-LDN-CE", "signal_time", 1)
    assert a != b


def test_different_scheme_different_seed():
    a = permutation_seed("SB-LDN-CE", "signal_time", 0)
    b = permutation_seed("SB-LDN-CE", "pnl_bootstrap", 0)
    assert a != b


def test_seed_range_63_bit():
    s = permutation_seed("SB-LDN-CE", "signal_time", 0)
    assert 0 <= s <= 0x7FFFFFFFFFFFFFFF
