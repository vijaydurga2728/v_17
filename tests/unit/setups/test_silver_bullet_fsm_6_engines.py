import pytest
from v17.setups.silver_bullet_fsm import SilverBulletFSM, SBSignal
from v17.setups.sb_engines import ENGINE_CATALOG
from v17.setups.sb_constants import SPREAD_GUARD_MULT, FVG_COST_VIABILITY_MULT


def _default_ctx(bias="BULLISH", blackout=False, spread_x_median=1.0, window_open=True,
                 sweep=True, fvg_kind="bullish", fvg_height=0.0005):
    spread = 0.00001
    median = spread / spread_x_median if spread_x_median > 0 else spread
    bottom = 1.1000
    top = bottom + fvg_height
    return {
        "d1_bias": bias,
        "atr_14": 0.0005,
        "spread": spread,
        "spread_median": median,
        "calendar_blackout": blackout,
        "window_open": window_open,
        "liquidity_pools": [],
        "fvgs": [],
        "sweep_confirmed": sweep,
        "swept_pool_kind": "session_low" if sweep else None,
        "displacement_bar_fvg": {"kind": fvg_kind, "top": top, "bottom": bottom,
                                 "ce": (top + bottom) / 2.0, "ts_ns": 0} if fvg_kind else None,
    }


def _bar():
    return {"ts_utc": 1700000000000000000, "bid_o": 1.10, "bid_h": 1.1005, "bid_l": 1.0999,
            "bid_c": 1.1004, "ask_o": 1.10002, "ask_h": 1.10052, "ask_l": 1.09992,
            "ask_c": 1.10042, "symbol": "EURUSD"}


@pytest.mark.parametrize("config", ENGINE_CATALOG, ids=lambda c: c.engine_id)
def test_fsm_instantiates_for_every_engine(config):
    fsm = SilverBulletFSM(config)
    assert fsm.engine_id == config.engine_id


@pytest.mark.parametrize("config", ENGINE_CATALOG, ids=lambda c: c.engine_id)
def test_fsm_returns_none_when_bias_none(config):
    fsm = SilverBulletFSM(config)
    bar = _bar()
    bar["symbol"] = config.symbols[0]
    sig = fsm.step(bar, _default_ctx(bias="NONE"))
    assert sig is None


@pytest.mark.parametrize("config", ENGINE_CATALOG, ids=lambda c: c.engine_id)
def test_fsm_returns_none_during_blackout(config):
    fsm = SilverBulletFSM(config)
    bar = _bar()
    bar["symbol"] = config.symbols[0]
    sig = fsm.step(bar, _default_ctx(blackout=True))
    assert sig is None


@pytest.mark.parametrize("config", ENGINE_CATALOG, ids=lambda c: c.engine_id)
def test_fsm_returns_none_on_spread_spike(config):
    fsm = SilverBulletFSM(config)
    bar = _bar()
    bar["symbol"] = config.symbols[0]
    # spread == 5x median → rejected (gate is >3x)
    sig = fsm.step(bar, _default_ctx(spread_x_median=5.0))
    assert sig is None


@pytest.mark.parametrize("config", ENGINE_CATALOG, ids=lambda c: c.engine_id)
def test_fsm_returns_none_when_window_closed(config):
    fsm = SilverBulletFSM(config)
    bar = _bar()
    bar["symbol"] = config.symbols[0]
    sig = fsm.step(bar, _default_ctx(window_open=False))
    assert sig is None


@pytest.mark.parametrize("config", ENGINE_CATALOG, ids=lambda c: c.engine_id)
def test_fsm_returns_none_when_no_sweep(config):
    fsm = SilverBulletFSM(config)
    bar = _bar()
    bar["symbol"] = config.symbols[0]
    sig = fsm.step(bar, _default_ctx(sweep=False))
    assert sig is None


@pytest.mark.parametrize("config", ENGINE_CATALOG, ids=lambda c: c.engine_id)
def test_fsm_returns_none_when_fvg_bias_mismatch(config):
    fsm = SilverBulletFSM(config)
    bar = _bar()
    bar["symbol"] = config.symbols[0]
    # Bullish bias but bearish FVG
    sig = fsm.step(bar, _default_ctx(bias="BULLISH", fvg_kind="bearish"))
    assert sig is None


@pytest.mark.parametrize("config", ENGINE_CATALOG, ids=lambda c: c.engine_id)
def test_fsm_returns_none_when_fvg_too_small_for_cost(config):
    fsm = SilverBulletFSM(config)
    bar = _bar()
    bar["symbol"] = config.symbols[0]
    # FVG height = 0.00001, spread = 0.00001 → height/spread = 1 < 2
    sig = fsm.step(bar, _default_ctx(fvg_height=0.00001))
    assert sig is None


def test_fsm_ce_entry_is_fvg_midpoint():
    cfg = [c for c in ENGINE_CATALOG if c.engine_id == "SB-NYAM-CE"][0]
    fsm = SilverBulletFSM(cfg)
    bar = _bar()
    bar["symbol"] = "EURUSD"
    sig = fsm.step(bar, _default_ctx(bias="BULLISH", fvg_kind="bullish", fvg_height=0.001))
    assert sig is not None
    assert sig.side == "LONG"
    # CE midpoint of bullish FVG [1.1000, 1.1010] = 1.1005
    assert abs(sig.entry_price - 1.1005) < 1e-9


def test_fsm_aggressive_entry_is_proximal_edge():
    cfg = [c for c in ENGINE_CATALOG if c.engine_id == "SB-NYAM-AG"][0]
    fsm = SilverBulletFSM(cfg)
    bar = _bar()
    bar["symbol"] = "EURUSD"
    sig = fsm.step(bar, _default_ctx(bias="BULLISH", fvg_kind="bullish", fvg_height=0.001))
    assert sig is not None
    # Aggressive long enters at proximal edge = top of bullish FVG
    assert abs(sig.entry_price - 1.1010) < 1e-9
