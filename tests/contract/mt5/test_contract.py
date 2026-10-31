from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from v17.common.dtos import OrderRequest, Tick
from v17.common.types import TF, Side, Symbol, Ticket
from v17.mt5.fake import FakeMT5
from v17.mt5.gateway import MT5Gateway
from v17.mt5.protocol import TradeGateway


def _now() -> datetime:
    return datetime(2026, 1, 2, 10, 0, tzinfo=UTC)


def _make_mock_mt5() -> MagicMock:
    m = MagicMock()
    m.initialize.return_value = True
    m.login.return_value = True
    m.shutdown.return_value = None
    m.symbol_select.return_value = True
    m.last_error.return_value = (-1, "mock error")
    m.symbol_info_tick.return_value = SimpleNamespace(
        time=int(_now().timestamp()), bid=1.10000, ask=1.10008,
    )
    m.copy_rates_from_pos.return_value = [
        SimpleNamespace(
            time=int(datetime(2026, 1, 2, 9, 0, tzinfo=UTC).timestamp()),
            open=1.10000, high=1.10050, low=1.09950, close=1.10020,
            tick_volume=100, real_volume=0, spread=8,
        )
    ]
    m.order_send.return_value = SimpleNamespace(retcode=10009, order=1001, price=1.10008, comment="")
    m.positions_get.return_value = []
    m.TRADE_ACTION_DEAL = 1
    m.TRADE_ACTION_SLTP = 6
    m.ORDER_TYPE_BUY = 0
    m.ORDER_TYPE_SELL = 1
    m.ORDER_TIME_GTC = 0
    m.ORDER_FILLING_IOC = 1
    m.TIMEFRAME_M1 = 1
    m.TIMEFRAME_M15 = 15
    m.TIMEFRAME_H1 = 16385
    m.TIMEFRAME_H4 = 16388
    m.TIMEFRAME_D1 = 16408
    m.TRADE_RETCODE_DONE = 10009
    return m


def _fake() -> FakeMT5:
    f = FakeMT5()
    f.set_tick(
        Symbol("EURUSD"),
        Tick(symbol=Symbol("EURUSD"), ts=_now(), bid=Decimal("1.10000"), ask=Decimal("1.10008")),
    )
    f.set_bars(Symbol("EURUSD"), TF.M1, [])
    return f


def _real() -> MT5Gateway:
    return MT5Gateway(login=1, password="x", server="s", _mt5=_make_mock_mt5())


@pytest.fixture(params=["fake", "real"])
def gw(request: pytest.FixtureRequest) -> TradeGateway:
    impl: TradeGateway
    if request.param == "fake":
        impl = _fake()
    else:
        impl = _real()
    impl.connect()
    return impl


def _buy_order() -> OrderRequest:
    return OrderRequest(
        symbol=Symbol("EURUSD"),
        side=Side.BUY,
        size_lots=Decimal("0.01"),
        sl=Decimal("1.09900"),
        tp=Decimal("1.10150"),
    )


class TestContractConnect:
    def test_connect_and_disconnect_no_error(self, gw: TradeGateway) -> None:
        gw.disconnect()
        gw.connect()


class TestContractSymbolSelect:
    def test_symbol_select_no_error(self, gw: TradeGateway) -> None:
        gw.symbol_select(Symbol("EURUSD"))


class TestContractTick:
    def test_tick_returns_tick_or_none(self, gw: TradeGateway) -> None:
        t = gw.tick(Symbol("EURUSD"))
        if t is not None:
            assert t.symbol == Symbol("EURUSD")
            assert t.ask >= t.bid


class TestContractRates:
    def test_rates_returns_list(self, gw: TradeGateway) -> None:
        result = gw.rates(Symbol("EURUSD"), TF.M1, 10)
        assert isinstance(result, list)
        for bar in result:
            assert bar.symbol == Symbol("EURUSD")
            assert bar.tf == TF.M1


class TestContractOrderSend:
    def test_order_send_ok_has_ticket_and_price(self, gw: TradeGateway) -> None:
        result = gw.order_send(_buy_order())
        assert result.ok
        assert result.ticket is not None
        assert result.filled_price is not None
        assert result.filled_at is not None


class TestContractPositions:
    def test_positions_after_open_is_list(self, gw: TradeGateway) -> None:
        gw.order_send(_buy_order())
        result = gw.positions()
        assert isinstance(result, list)


class TestContractModify:
    def test_modify_ok(self, gw: TradeGateway) -> None:
        r = gw.order_send(_buy_order())
        assert r.ticket is not None
        result = gw.order_modify(r.ticket, Decimal("1.098"), Decimal("1.103"))
        assert result.ok


class TestContractClose:
    def test_close_unknown_returns_not_ok(self, gw: TradeGateway) -> None:
        result = gw.order_close(Ticket(99999))
        assert not result.ok
        assert result.error_code is not None


def test_isinstance_trade_gateway_fake() -> None:
    assert isinstance(FakeMT5(), TradeGateway)


def test_isinstance_trade_gateway_real() -> None:
    gw = MT5Gateway(login=1, password="x", server="s", _mt5=_make_mock_mt5())
    assert isinstance(gw, TradeGateway)
