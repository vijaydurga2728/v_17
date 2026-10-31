from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from v17.common.dtos import Zone
from v17.common.types import TF, Side
from v17.setups.judas_swing import _pick_zone as _pick_zone_judas
from v17.setups.silver_bullet import _pick_zone as _pick_zone_sb

_NOW = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
_PAST = _NOW - timedelta(hours=1)
_FUTURE = _NOW + timedelta(hours=1)


def _zone(
    side: Side,
    top: Decimal,
    bottom: Decimal,
    mitigated_at: datetime | None = None,
) -> Zone:
    return Zone(
        kind="fvg",
        side=side,
        tf=TF.M15,
        created_at=_PAST,
        top=top,
        bottom=bottom,
        mitigated_at=mitigated_at,
    )


class TestPickZoneTolerance:
    def test_fires_when_price_inside_zone(self) -> None:
        zone = _zone(Side.BUY, Decimal("1.1060"), Decimal("1.1040"))
        for fn in (_pick_zone_sb, _pick_zone_judas):
            assert fn([zone], Side.BUY, Decimal("1.1050"), _NOW) is zone

    def test_fires_when_price_within_10_pips_below_zone(self) -> None:
        # price = 1.1035, zone bottom = 1.1040 → 5 pips below → within tolerance
        zone = _zone(Side.BUY, Decimal("1.1060"), Decimal("1.1040"))
        for fn in (_pick_zone_sb, _pick_zone_judas):
            assert fn([zone], Side.BUY, Decimal("1.1035"), _NOW) is zone

    def test_fires_when_price_within_10_pips_above_zone(self) -> None:
        # price = 1.1065, zone top = 1.1060 → 5 pips above → within tolerance
        zone = _zone(Side.BUY, Decimal("1.1060"), Decimal("1.1040"))
        for fn in (_pick_zone_sb, _pick_zone_judas):
            assert fn([zone], Side.BUY, Decimal("1.1065"), _NOW) is zone

    def test_skips_when_price_outside_10_pip_tolerance(self) -> None:
        # price = 1.1072, zone top = 1.1060 → 12 pips above → outside 10-pip tolerance
        zone = _zone(Side.BUY, Decimal("1.1060"), Decimal("1.1040"))
        for fn in (_pick_zone_sb, _pick_zone_judas):
            assert fn([zone], Side.BUY, Decimal("1.1072"), _NOW) is None

    def test_skips_zone_mitigated_before_now(self) -> None:
        # mitigation at _PAST (before _NOW) → zone IS mitigated → skip
        zone = _zone(Side.BUY, Decimal("1.1060"), Decimal("1.1040"), mitigated_at=_PAST)
        for fn in (_pick_zone_sb, _pick_zone_judas):
            assert fn([zone], Side.BUY, Decimal("1.1050"), _NOW) is None

    def test_fires_when_zone_mitigation_is_in_future(self) -> None:
        # mitigation flagged at _FUTURE (after _NOW) → lookahead-safe: use zone now
        zone = _zone(Side.BUY, Decimal("1.1060"), Decimal("1.1040"), mitigated_at=_FUTURE)
        for fn in (_pick_zone_sb, _pick_zone_judas):
            assert fn([zone], Side.BUY, Decimal("1.1050"), _NOW) is zone

    def test_skips_side_mismatch(self) -> None:
        zone = _zone(Side.SELL, Decimal("1.1060"), Decimal("1.1040"))
        for fn in (_pick_zone_sb, _pick_zone_judas):
            assert fn([zone], Side.BUY, Decimal("1.1050"), _NOW) is None

    def test_picks_closest_zone_when_multiple_match(self) -> None:
        far = _zone(Side.BUY, Decimal("1.1030"), Decimal("1.1020"))  # 5 pips below 1.1035
        near = _zone(Side.BUY, Decimal("1.1040"), Decimal("1.1030"))  # price 1.1035 inside
        for fn in (_pick_zone_sb, _pick_zone_judas):
            picked = fn([far, near], Side.BUY, Decimal("1.1035"), _NOW)
            assert picked is near
