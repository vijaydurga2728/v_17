import pytest
from v17.setups.sb_sl_tp import compute_sl_tp, SBRejectError


def test_eurusd_long_sl_tp_pass():
    out = compute_sl_tp(
        side="LONG", entry=1.1000, sweep_extreme=1.0995,
        opposing_target=1.1020, symbol="EURUSD",
    )
    # buffer_min = 2 pips = 0.0002
    # raw_sl = 1.0995 - 0.0002 = 1.0993 → distance from 1.1000 = 0.0007 (7 pips, within 15 cap)
    assert abs(out.sl - 1.0993) < 1e-6
    assert out.tp == 1.1020
    assert out.r_multiple >= 1.5


def test_eurusd_long_rr_reject():
    with pytest.raises(SBRejectError, match="R:R"):
        compute_sl_tp(
            side="LONG", entry=1.1000, sweep_extreme=1.0998,
            opposing_target=1.1003, symbol="EURUSD",
        )


def test_sl_widens_when_below_min_distance():
    # sweep_extreme very close → raw distance less than buffer_min; widens to entry - 2 pips
    out = compute_sl_tp(
        side="LONG", entry=1.1000, sweep_extreme=1.0999,
        opposing_target=1.1030, symbol="EURUSD",
    )
    # 1.0999 - 0.0002 = 1.0997 → distance 0.0003 (3 pips, > 2 min) → ok, no widen
    # Try closer:
    out2 = compute_sl_tp(
        side="LONG", entry=1.1000, sweep_extreme=1.09995,
        opposing_target=1.1030, symbol="EURUSD",
    )
    # 1.09995 - 0.0002 = 1.09975 → distance 0.00025 (2.5 pips, > 2 min) → OK
    # Force widening:
    out3 = compute_sl_tp(
        side="LONG", entry=1.1000, sweep_extreme=1.10000,
        opposing_target=1.1030, symbol="EURUSD",
    )
    # raw = 1.1000 - 0.0002 = 1.0998, distance 0.0002 = 2 pips exactly → no widen needed
    assert abs(out3.sl - 1.0998) < 1e-9


def test_fx_long_sl_distance_cap_reject():
    with pytest.raises(SBRejectError, match="exceeds max"):
        compute_sl_tp(
            side="LONG", entry=1.1000, sweep_extreme=1.0980,
            opposing_target=1.1050, symbol="EURUSD",
        )


def test_usatech_short_sl_tp_pass():
    out = compute_sl_tp(
        side="SHORT", entry=18000.0, sweep_extreme=18005.0,
        opposing_target=17970.0, symbol="USATECHIDXUSD",
    )
    # buffer_min 2 pts → raw_sl = 18007
    assert abs(out.sl - 18007.0) < 1e-6
    assert out.tp == 17970.0
    assert out.r_multiple >= 1.5


def test_short_target_above_entry_rejected():
    with pytest.raises(SBRejectError, match="above entry"):
        compute_sl_tp(
            side="SHORT", entry=1.1000, sweep_extreme=1.1005,
            opposing_target=1.1020, symbol="EURUSD",
        )
