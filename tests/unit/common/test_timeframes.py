from v17.common.timeframes import TF_ORDER, pandas_offset, tf_minutes
from v17.common.types import TF


def test_pandas_offset() -> None:
    assert pandas_offset(TF.M1) == "1min"
    assert pandas_offset(TF.M5) == "5min"
    assert pandas_offset(TF.M15) == "15min"
    assert pandas_offset(TF.H1) == "1h"
    assert pandas_offset(TF.H4) == "4h"
    assert pandas_offset(TF.D1) == "1D"


def test_tf_minutes() -> None:
    assert tf_minutes(TF.M1) == 1
    assert tf_minutes(TF.M5) == 5
    assert tf_minutes(TF.M15) == 15
    assert tf_minutes(TF.H1) == 60
    assert tf_minutes(TF.H4) == 240
    assert tf_minutes(TF.D1) == 1440


def test_tf_order_ascending() -> None:
    assert TF_ORDER == (TF.M1, TF.M5, TF.M15, TF.H1, TF.H4, TF.D1)
