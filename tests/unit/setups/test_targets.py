from decimal import Decimal

from v17.common.types import Side
from v17.setups.targets import passes_rr, pip_distance, rr


def test_rr_long() -> None:
    assert rr(Decimal("1.10"), Decimal("1.09"), Decimal("1.115"), Side.BUY) == Decimal("1.5")


def test_rr_short() -> None:
    assert rr(Decimal("1.10"), Decimal("1.11"), Decimal("1.085"), Side.SELL) == Decimal("1.5")


def test_pip_distance() -> None:
    assert pip_distance(Decimal("1.1050"), Decimal("1.1000")) == Decimal("50")


def test_passes_rr() -> None:
    assert passes_rr(Decimal("1.6"))
    assert not passes_rr(Decimal("1.4"))
