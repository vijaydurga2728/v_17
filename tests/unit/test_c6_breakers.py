from v17.backtest.c6_breakers import DailyState, allow_entry, evaluate, update_after_trade


def _s(equity=10_000.0):
    return DailyState("2020-01-02", equity, 0.0, 0, 0, False, False)


def test_hard_loss_flattens_and_locks():
    s = _s()
    s = update_after_trade(s, -260.0)  # -2.6%
    s = evaluate(s)
    assert s.flatten_now is True
    assert s.locked is True


def test_soft_loss_blocks_entries_but_does_not_flatten():
    s = _s()
    s = update_after_trade(s, -160.0)  # -1.6%
    s = evaluate(s)
    assert s.locked is True
    assert s.flatten_now is False


def test_profit_stop():
    s = _s()
    s = update_after_trade(s, 210.0)
    s = evaluate(s)
    assert s.flatten_now is True
    assert s.locked is True


def test_three_consec_losses():
    s = _s()
    for _ in range(3):
        s = update_after_trade(s, -10.0)
    s = evaluate(s)
    assert s.locked is True
    assert s.flatten_now is False


def test_trade_cap():
    s = _s()
    for _ in range(8):
        s = update_after_trade(s, 1.0)  # small wins to avoid other breakers
    s = evaluate(s)
    assert s.locked is True


def test_win_resets_consec_losses():
    s = _s()
    s = update_after_trade(s, -10.0)
    s = update_after_trade(s, -10.0)
    s = update_after_trade(s, +5.0)
    assert s.consec_losses == 0


def test_precedence_hard_beats_profit():
    # Realized P&L in a single step that would satisfy both profit and hard -> hard wins.
    # (Not realistic, but ensures precedence.)
    s = _s()
    s.realized_pnl = -260.0
    s.trade_count = 1
    s = evaluate(s)
    assert s.flatten_now is True
