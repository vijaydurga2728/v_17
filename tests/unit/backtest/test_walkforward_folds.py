import pandas as pd
from v17.backtest.walkforward import generate_folds


def test_seven_folds_generated():
    folds = generate_folds()
    assert len(folds) == 7


def test_fold_1_train_2015_2017_oos_2018():
    folds = generate_folds()
    f1 = folds[0]
    assert f1.train_start == pd.Timestamp("2015-01-01", tz="UTC").value
    assert f1.oos_start == pd.Timestamp("2018-01-01", tz="UTC").value
    assert f1.oos_end == pd.Timestamp("2019-01-01", tz="UTC").value


def test_fold_7_train_2015_2023_oos_2024():
    folds = generate_folds()
    f7 = folds[6]
    assert f7.oos_start == pd.Timestamp("2024-01-01", tz="UTC").value
    assert f7.oos_end == pd.Timestamp("2025-01-01", tz="UTC").value


def test_no_fold_touches_holdout():
    folds = generate_folds()
    holdout_start = pd.Timestamp("2025-01-01", tz="UTC").value
    for f in folds:
        assert f.oos_end <= holdout_start


def test_all_folds_share_train_start_2015():
    folds = generate_folds()
    ts0 = pd.Timestamp("2015-01-01", tz="UTC").value
    for f in folds:
        assert f.train_start == ts0
