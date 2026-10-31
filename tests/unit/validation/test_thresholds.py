from v17.validation.thresholds import VALIDATION_THRESHOLDS


def test_locked_values() -> None:
    t = VALIDATION_THRESHOLDS
    assert t["min_pf"] == 1.8
    assert t["min_sharpe"] == 2.0
    assert t["max_dd_pct"] == 6.0
    assert t["min_winrate"] == 0.50
    assert t["min_mc_p5_pf"] == 1.3
    assert t["max_mc_p95_dd_pct"] == 8.0
    assert t["min_oos_trades"] == 200
    assert t["min_folds_passed"] == 4
