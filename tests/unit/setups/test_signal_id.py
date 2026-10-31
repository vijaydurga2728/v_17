from datetime import UTC, datetime

from v17.common.types import Side, Symbol
from v17.setups.signal_id import make_signal_id


def test_deterministic() -> None:
    at = datetime(2026, 10, 28, 8, 30, tzinfo=UTC)
    a = make_signal_id(Symbol("EURUSD"), "silver_bullet", at, Side.BUY)
    b = make_signal_id(Symbol("EURUSD"), "silver_bullet", at, Side.BUY)
    assert a == b and len(a) == 16


def test_different_inputs_differ() -> None:
    at = datetime(2026, 10, 28, 8, 30, tzinfo=UTC)
    a = make_signal_id(Symbol("EURUSD"), "silver_bullet", at, Side.BUY)
    b = make_signal_id(Symbol("GBPUSD"), "silver_bullet", at, Side.BUY)
    assert a != b
