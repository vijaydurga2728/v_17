from datetime import UTC, datetime

from v17.backtest.walkforward import anchored_folds


def test_12_folds_shape() -> None:
    start = datetime(2015, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    folds = anchored_folds(start, end, n_folds=12, is_pct=0.6)
    assert len(folds) == 12
    assert all(f["is_start"] == start for f in folds)
    assert folds[-1]["oos_end"] == end


def test_fold_order_strict() -> None:
    start = datetime(2015, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    folds = anchored_folds(start, end, n_folds=12, is_pct=0.6)
    for f in folds:
        assert f["is_start"] < f["is_end"] < f["oos_end"]
        assert f["oos_start"] == f["is_end"]
