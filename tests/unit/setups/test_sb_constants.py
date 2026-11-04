from v17.setups import sb_constants as c


def test_constants_match_spec_section_5():
    assert c.D1_EMA_PERIOD == 20
    assert c.D1_STRUCTURE_SWING_LOOKBACK_DAYS == 20
    assert c.ATR_PERIOD_M1 == 14
    assert c.DISPLACEMENT_BODY_RATIO_MIN == 0.65
    assert c.DISPLACEMENT_RANGE_ATR_MULT == 1.5
    assert c.FVG_COST_VIABILITY_MULT == 2.0
    assert c.MIN_R_MULTIPLE == 1.5
    assert c.STRUCTURAL_FALLBACK_USATECH_PTS == 15
    assert c.STRUCTURAL_FALLBACK_FX_PIPS == 20
    assert c.SL_BUFFER_FX_MIN_PIPS == 2.0
    assert c.SL_BUFFER_FX_MAX_PIPS == 15.0
    assert c.SL_BUFFER_USATECH_MAX_PTS == 20.0
    assert c.PENDING_EXPIRY_MIN_AFTER_WINDOW == 5
    assert c.POSITION_HARD_EXIT_MIN_AFTER_WINDOW == 60
    assert c.NEWS_BLACKOUT_BEFORE_MIN == 10
    assert c.NEWS_BLACKOUT_AFTER_MIN == 20
    assert c.SPREAD_GUARD_LOOKBACK_DAYS == 30
    assert c.SPREAD_GUARD_MULT == 3.0
    assert c.DAILY_LOSS_SOFT_STOP == 0.04
    assert c.TOTAL_LOSS_HARD_FREEZE == 0.08
    assert c.RISK_PER_TRADE == 0.005


def test_constants_module_is_frozen():
    import inspect
    source = inspect.getsource(c)
    assert "class " not in source
    assert "dataclass" not in source
