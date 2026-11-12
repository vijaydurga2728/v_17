from v17.backtest.c6_position import C6Position, step


def _bar(o, h, l, c, bid_c=None, ask_c=None, ts=0):
    return {
        "ts_utc": ts,
        "bid_o": o, "bid_h": h, "bid_l": l, "bid_c": bid_c or c,
        "ask_o": o, "ask_h": h, "ask_l": l, "ask_c": ask_c or c,
    }


def _long_pos(entry=0.6500, stop=0.6480, r=0.002, lots=0.1):
    return C6Position(
        trade_id="t1", symbol="AUDUSD", side="long",
        entry_ts_ns=0, entry_price=entry, initial_stop=stop,
        r_price=r, lots_a=lots, lots_b=lots,
        leg_a_open=True, leg_b_open=True, leg_b_stop=stop,
        breakeven_hit=False, exit_log=[],
    )


def test_leg_a_hits_target():
    pos = _long_pos()
    bar = _bar(0.6500, 0.6525, 0.6495, 0.6515)  # high sweeps 1R = 0.6520
    out = step(pos, bar, ema20=0.6505, atr=0.0015, is_hard_flat=False)
    events = [e for e in out.exit_log if e["leg"] == "A"]
    assert len(events) == 1
    assert events[0]["reason"] == "target_1R"
    assert out.leg_a_open is False
    assert out.breakeven_hit is True
    # Leg B stop moved to entry.
    assert out.leg_b_stop == pos.entry_price


def test_initial_stop_both_legs_exit():
    pos = _long_pos()
    bar = _bar(0.6500, 0.6505, 0.6475, 0.6482)  # low breaches initial stop 0.6480
    out = step(pos, bar, ema20=0.6505, atr=0.0015, is_hard_flat=False)
    assert out.leg_a_open is False
    assert out.leg_b_open is False
    reasons = {e["reason"] for e in out.exit_log}
    assert "initial_stop" in reasons


def test_leg_b_trail_activates_only_after_leg_a():
    pos = _long_pos()
    # Bar does not reach 1R target; leg_b_stop should stay at initial.
    bar = _bar(0.6500, 0.6510, 0.6495, 0.6508)
    out = step(pos, bar, ema20=0.6505, atr=0.0015, is_hard_flat=False)
    assert out.leg_a_open is True
    assert out.leg_b_stop == pos.initial_stop  # not trailed


def test_trail_ratchets_up_only_after_leg_a_filled():
    pos = _long_pos()
    pos.leg_a_open = False
    pos.breakeven_hit = True
    pos.leg_b_stop = pos.entry_price
    bar = _bar(0.6500, 0.6540, 0.6495, 0.6535)
    # ema20 - 0.25*atr = 0.6530 - 0.000375 = 0.652625 > entry 0.6500 -> ratchet up.
    out = step(pos, bar, ema20=0.6530, atr=0.0015, is_hard_flat=False)
    assert out.leg_b_stop > pos.entry_price


def test_hard_flat_closes_both():
    pos = _long_pos()
    bar = _bar(0.6500, 0.6505, 0.6495, 0.6502)
    out = step(pos, bar, ema20=0.6505, atr=0.0015, is_hard_flat=True)
    assert out.leg_a_open is False
    assert out.leg_b_open is False
    reasons = {e["reason"] for e in out.exit_log}
    assert "time_stop" in reasons
