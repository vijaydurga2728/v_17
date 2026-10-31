from v17.common.types import TF, Bias, Side, Symbol


def test_symbol_newtype() -> None:
    s: Symbol = Symbol("EURUSD")
    assert isinstance(s, str) and s == "EURUSD"


def test_tf_enum_values() -> None:
    assert TF.M1.value == "1m"
    assert TF.M15.value == "15m"
    assert TF.H1.value == "1h"
    assert TF.H4.value == "4h"
    assert TF.D1.value == "1d"


def test_side_bias_enums() -> None:
    assert Side.BUY.value == "buy" and Side.SELL.value == "sell"
    assert set(Bias) == {Bias.BULL, Bias.BEAR, Bias.NONE}
