from decimal import Decimal

from v17.risk.sizing import compute_lots


def test_sizing_standard_case() -> None:
    lots = compute_lots(
        Decimal("100000"),
        Decimal("1.0"),
        Decimal("10"),
        Decimal("10"),
        Decimal("0.01"),
        Decimal("0.01"),
    )
    assert lots == Decimal("10.00")


def test_sizing_floor_to_step() -> None:
    lots = compute_lots(
        Decimal("100000"),
        Decimal("1.0"),
        Decimal("13"),
        Decimal("10"),
        Decimal("0.01"),
        Decimal("0.01"),
    )
    assert lots == Decimal("7.69")


def test_sizing_small_account() -> None:
    lots = compute_lots(
        Decimal("1000"),
        Decimal("1.0"),
        Decimal("10"),
        Decimal("10"),
        Decimal("0.01"),
        Decimal("0.01"),
    )
    assert lots == Decimal("0.10")


def test_sizing_zero_when_below_min() -> None:
    lots = compute_lots(
        Decimal("100"),
        Decimal("1.0"),
        Decimal("50"),
        Decimal("10"),
        Decimal("0.01"),
        Decimal("0.01"),
    )
    assert lots == Decimal("0")
