from v17.risk.sb_risk_engine import SBRiskEngine


def test_daily_loss_soft_stop_freezes_until_next_day():
    r = SBRiskEngine(starting_equity=10_000.0)
    r.start_of_day(1_700_000_000_000_000_000)
    assert r.allow_trade()
    # Trade loses 4.5% of start-of-day equity
    r.on_trade_close(pnl_cash=-450.0, trade_date_utc_ns=1_700_000_000_000_000_000)
    assert not r.allow_trade()


def test_daily_lock_clears_next_day():
    r = SBRiskEngine(starting_equity=10_000.0)
    r.start_of_day(1_700_000_000_000_000_000)
    r.on_trade_close(pnl_cash=-450.0, trade_date_utc_ns=1_700_000_000_000_000_000)
    assert not r.allow_trade()
    # Advance one full day
    r.start_of_day(1_700_000_000_000_000_000 + 86_400_000_000_000)
    assert r.allow_trade()


def test_total_loss_8pct_permanent_freeze():
    r = SBRiskEngine(starting_equity=10_000.0)
    r.start_of_day(1_700_000_000_000_000_000)
    r.update_peak_equity(10_000.0)
    r.on_trade_close(pnl_cash=-850.0, trade_date_utc_ns=1_700_000_000_000_000_000)
    assert not r.allow_trade()
    # Even after day change, still frozen
    r.start_of_day(1_700_000_000_000_000_000 + 86_400_000_000_000)
    assert not r.allow_trade()


def test_profit_within_bounds_keeps_trading_allowed():
    r = SBRiskEngine(starting_equity=10_000.0)
    r.start_of_day(1_700_000_000_000_000_000)
    r.on_trade_close(pnl_cash=50.0, trade_date_utc_ns=1_700_000_000_000_000_000)
    assert r.allow_trade()
    assert r.equity == 10_050.0


def test_daily_soft_stop_exactly_at_threshold_triggers():
    # pnl exactly -4% of SOD equity triggers (spec: `<=`, implementation: `<= -DAILY_LOSS_SOFT_STOP`)
    r = SBRiskEngine(starting_equity=10_000.0)
    r.start_of_day(1_700_000_000_000_000_000)
    r.on_trade_close(pnl_cash=-400.0, trade_date_utc_ns=1_700_000_000_000_000_000)
    assert not r.allow_trade()
