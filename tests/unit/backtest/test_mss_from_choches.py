from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from v17.backtest.precompute import _mss_from_choches
from v17.common.dtos import Swing, Zone
from v17.common.types import TF, Side


def _choch(at: datetime, side: Side, price: Decimal) -> Swing:
    return Swing(kind="choch", side=side, tf=TF.M1, at=at, price=price)


def _zone(created_at: datetime, side: Side, top: Decimal, bottom: Decimal) -> Zone:
    return Zone(
        kind="fvg",
        side=side,
        tf=TF.M15,
        top=top,
        bottom=bottom,
        created_at=created_at,
        mitigated_at=None,
    )


# Current spec: MSS emits for every CHoCH within _MSS_WINDOW_MIN (= 30) of `now`.
# Zone-containment / zone-side / zone-mitigation are NOT checked here — those
# are separate confluences evaluated at setup level by `_pick_zone`.


class TestMSSFromChoches:
    def test_fires_for_choch_in_window(self) -> None:
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        choch_at = now - timedelta(minutes=3)
        choches = [_choch(choch_at, Side.BUY, Decimal("1.1050"))]
        result = _mss_from_choches(choches, [], now)
        assert len(result) == 1
        assert result[0].kind == "mss"
        assert result[0].side == Side.BUY
        assert result[0].at == choch_at

    def test_window_excludes_old_choches(self) -> None:
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        # 31 min ago is outside the 30-min window
        choch_at = now - timedelta(minutes=31)
        choches = [_choch(choch_at, Side.BUY, Decimal("1.1050"))]
        result = _mss_from_choches(choches, [], now)
        assert result == []

    def test_window_includes_edge_30_min(self) -> None:
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        # Exactly 29 min ago is inside the 30-min window
        choch_at = now - timedelta(minutes=29)
        choches = [_choch(choch_at, Side.BUY, Decimal("1.1050"))]
        result = _mss_from_choches(choches, [], now)
        assert len(result) == 1

    def test_future_choch_excluded(self) -> None:
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        future_choch = _choch(now + timedelta(minutes=5), Side.BUY, Decimal("1.1050"))
        result = _mss_from_choches([future_choch], [], now)
        assert result == []

    def test_zones_ignored_mss_fires_regardless(self) -> None:
        # Even with a side-mismatched or mitigated or absent zone, MSS still fires.
        # Zone-containment is a setup-level concern, not an MSS-generation concern.
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        choch_at = now - timedelta(minutes=3)
        choches = [_choch(choch_at, Side.BUY, Decimal("1.1050"))]
        side_mismatch_zone = _zone(
            choch_at - timedelta(minutes=30),
            Side.SELL,
            Decimal("1.1060"),
            Decimal("1.1040"),
        )
        result = _mss_from_choches(choches, [side_mismatch_zone], now)
        assert len(result) == 1

    def test_multiple_choches_in_window_all_emit(self) -> None:
        # CHoCH list must be sorted ascending by `at` (bisect assumption).
        now = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        choches = [
            _choch(now - timedelta(minutes=35), Side.BUY, Decimal("1.1045")),  # outside 30
            _choch(now - timedelta(minutes=20), Side.BUY, Decimal("1.1050")),
            _choch(now - timedelta(minutes=10), Side.SELL, Decimal("1.1055")),
        ]
        result = _mss_from_choches(choches, [], now)
        assert len(result) == 2
        assert {r.side for r in result} == {Side.BUY, Side.SELL}
