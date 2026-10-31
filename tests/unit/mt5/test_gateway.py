from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from v17.common.dtos import OrderRequest
from v17.common.errors import V17GatewayDisconnected, V17GatewayError
from v17.common.types import TF, Side, Symbol, Ticket
from v17.mt5.gateway import MT5Gateway


def _make_mt5_mock() -> MagicMock:
    """Minimal mock of the MetaTrader5 module."""
    m = MagicMock()
    m.initialize.return_value = True
    m.login.return_value = True
    m.shutdown.return_value = None
    m.symbol_select.return_value = True
    m.last_error.return_value = (-1, "mock error")
    # Tick
    m.symbol_info_tick.return_value = SimpleNamespace(
        time=int(datetime(2026, 1, 2, 10, 0, tzinfo=UTC).timestamp()),
        bid=1.10000,
        ask=1.10008,
    )
    # Rates: return a single-row structured array-like
    m.copy_rates_from_pos.return_value = [
        SimpleNamespace(
            time=int(datetime(2026, 1, 2, 9, 0, tzinfo=UTC).timestamp()),
            open=1.10000, high=1.10050, low=1.09950, close=1.10020,
            tick_volume=100, real_volume=0, spread=8,
        )
    ]
    # Order send
    m.order_send.return_value = SimpleNamespace(
        retcode=10009,  # TRADE_RETCODE_DONE
        order=1001,
        price=1.10008,
        comment="",
    )
    # Positions
    m.positions_get.return_value = []
    # Constants
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


def _gw(mock_mt5: MagicMock | None = None) -> MT5Gateway:
    if mock_mt5 is None:
        mock_mt5 = _make_mt5_mock()
    return MT5Gateway(login=12345, password="secret", server="Demo-Server", _mt5=mock_mt5)


class TestMT5GatewayConnect:
    def test_connect_calls_initialize(self) -> None:
        m = _make_mt5_mock()
        gw = _gw(m)
        gw.connect()
        m.initialize.assert_called_once()

    def test_connect_failure_raises_gateway_error(self) -> None:
        m = _make_mt5_mock()
        m.initialize.return_value = False
        gw = _gw(m)
        with pytest.raises(V17GatewayError):
            gw.connect()

    def test_disconnect_calls_shutdown(self) -> None:
        m = _make_mt5_mock()
        gw = _gw(m)
        gw.connect()
        gw.disconnect()
        m.shutdown.assert_called()


class TestMT5GatewayTick:
    def test_tick_returns_tick_dto(self) -> None:
        m = _make_mt5_mock()
        gw = _gw(m)
        gw.connect()
        t = gw.tick(Symbol("EURUSD"))
        assert t is not None
        assert t.bid == Decimal("1.1")
        assert t.ask == Decimal("1.10008")

    def test_tick_returns_none_when_mt5_returns_none(self) -> None:
        m = _make_mt5_mock()
        m.symbol_info_tick.return_value = None
        gw = _gw(m)
        gw.connect()
        assert gw.tick(Symbol("EURUSD")) is None


class TestMT5GatewayRates:
    def test_rates_returns_bars(self) -> None:
        m = _make_mt5_mock()
        gw = _gw(m)
        gw.connect()
        bars = gw.rates(Symbol("EURUSD"), TF.M1, 1)
        assert len(bars) == 1
        assert bars[0].symbol == Symbol("EURUSD")
        assert bars[0].tf == TF.M1

    def test_rates_empty_when_mt5_returns_none(self) -> None:
        m = _make_mt5_mock()
        m.copy_rates_from_pos.return_value = None
        gw = _gw(m)
        gw.connect()
        assert gw.rates(Symbol("EURUSD"), TF.M1, 10) == []


class TestMT5GatewayOrderSend:
    def _order(self) -> OrderRequest:
        return OrderRequest(
            symbol=Symbol("EURUSD"),
            side=Side.BUY,
            size_lots=Decimal("0.01"),
            sl=Decimal("1.09900"),
            tp=Decimal("1.10150"),
        )

    def test_order_send_returns_ok_result(self) -> None:
        m = _make_mt5_mock()
        gw = _gw(m)
        gw.connect()
        result = gw.order_send(self._order())
        assert result.ok
        assert result.ticket == Ticket(1001)

    def test_order_send_failure_returns_not_ok(self) -> None:
        m = _make_mt5_mock()
        m.order_send.return_value = SimpleNamespace(retcode=10006, order=None, price=0.0, comment="requote")
        gw = _gw(m)
        gw.connect()
        result = gw.order_send(self._order())
        assert not result.ok
        assert result.error_code == 10006


class TestMT5GatewayModify:
    def test_modify_returns_ok(self) -> None:
        m = _make_mt5_mock()
        m.order_send.return_value = SimpleNamespace(retcode=10009, order=1001, price=0.0, comment="")
        gw = _gw(m)
        gw.connect()
        result = gw.order_modify(Ticket(1001), Decimal("1.098"), Decimal("1.103"))
        assert result.ok

    def test_modify_failure_returns_not_ok(self) -> None:
        m = _make_mt5_mock()
        m.order_send.return_value = SimpleNamespace(retcode=10004, order=None, price=0.0, comment="no changes")
        gw = _gw(m)
        gw.connect()
        result = gw.order_modify(Ticket(1001), Decimal("1.098"), Decimal("1.103"))
        assert not result.ok


class TestMT5GatewayClose:
    def test_close_returns_ok(self) -> None:
        m = _make_mt5_mock()
        # positions_get returns one open position to close
        m.positions_get.return_value = [
            SimpleNamespace(
                ticket=1001, symbol="EURUSD", volume=0.01, type=0,  # ORDER_TYPE_BUY=0
                price_open=1.10008, sl=1.099, tp=1.1015, profit=0.0,
                time=int(datetime(2026, 1, 2, 10, 0, tzinfo=UTC).timestamp()),
            )
        ]
        m.order_send.return_value = SimpleNamespace(retcode=10009, order=1001, price=1.10000, comment="")
        gw = _gw(m)
        gw.connect()
        result = gw.order_close(Ticket(1001))
        assert result.ok

    def test_close_no_position_returns_not_ok(self) -> None:
        m = _make_mt5_mock()
        m.positions_get.return_value = None
        gw = _gw(m)
        gw.connect()
        result = gw.order_close(Ticket(999))
        assert not result.ok
        assert result.error_code == 2


class TestMT5GatewayPositions:
    def test_positions_empty(self) -> None:
        m = _make_mt5_mock()
        gw = _gw(m)
        gw.connect()
        assert gw.positions() == []

    def test_positions_returns_list(self) -> None:
        m = _make_mt5_mock()
        m.positions_get.return_value = [
            SimpleNamespace(
                ticket=1001, symbol="EURUSD", volume=0.01, type=0,
                price_open=1.10008, sl=1.099, tp=1.1015, profit=5.0,
                time=int(datetime(2026, 1, 2, 10, 0, tzinfo=UTC).timestamp()),
            )
        ]
        gw = _gw(m)
        gw.connect()
        result = gw.positions()
        assert len(result) == 1
        assert result[0].ticket == Ticket(1001)


class TestMT5GatewayReconnect:
    def test_reconnect_retries_on_disconnect(self) -> None:
        m = _make_mt5_mock()
        # First initialize fails (simulates disconnect), second succeeds
        m.initialize.side_effect = [False, True]
        m.last_error.return_value = (-1, "connection lost")
        gw = _gw(m)
        # First connect attempt fails; gateway should retry once internally
        # For this test, we manually call connect twice to verify retry logic
        with pytest.raises(V17GatewayError):
            gw.connect()
        # second attempt succeeds
        m.initialize.side_effect = None
        m.initialize.return_value = True
        gw.connect()
        assert m.initialize.call_count == 2


class TestMT5GatewayReconnectLoop:
    def test_worker_retries_on_disconnect(self) -> None:
        from unittest.mock import patch

        m = _make_mt5_mock()
        gw = _gw(m)
        gw.connect()
        # Simulate: first tick call returns None with disconnect error,
        # second call succeeds after reconnect
        call_count = 0
        original_tick = m.symbol_info_tick.return_value

        def flaky_tick(sym: str) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                m.last_error.return_value = (-10003, "connection lost")
                return None
            m.last_error.return_value = (-1, "ok")
            return original_tick

        m.symbol_info_tick.side_effect = flaky_tick
        with patch("v17.mt5.gateway.time.sleep"):
            result = gw.tick(Symbol("EURUSD"))
        # After reconnect, second call succeeds
        assert result is not None
        assert call_count == 2
