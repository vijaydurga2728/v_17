from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from v17.common.dtos import Bar, OrderRequest, OrderResult, Position, Tick
from v17.common.errors import V17GatewayDisconnected
from v17.common.types import TF, Side, Symbol, Ticket
from v17.mt5.fake import FakeMT5


def _now() -> datetime:
    return datetime(2026, 1, 2, 10, 0, tzinfo=UTC)


def _tick(bid: str = "1.10000", ask: str = "1.10008") -> Tick:
    return Tick(
        symbol=Symbol("EURUSD"),
        ts=_now(),
        bid=Decimal(bid),
        ask=Decimal(ask),
    )


def _bar(i: int = 0) -> Bar:
    base = Decimal("1.1") + Decimal(str(i)) * Decimal("0.001")
    return Bar(
        symbol=Symbol("EURUSD"),
        tf=TF.M1,
        ts=datetime(2026, 1, 2, 9, i, tzinfo=UTC),
        open=base,
        high=base + Decimal("0.0005"),
        low=base - Decimal("0.0005"),
        close=base + Decimal("0.0002"),
    )


def _order(side: Side = Side.BUY) -> OrderRequest:
    if side == Side.BUY:
        sl, tp = Decimal("1.09900"), Decimal("1.10150")
    else:
        sl, tp = Decimal("1.10150"), Decimal("1.09900")
    return OrderRequest(
        symbol=Symbol("EURUSD"),
        side=side,
        size_lots=Decimal("0.01"),
        sl=sl,
        tp=tp,
    )


class TestFakeMT5Connect:
    def test_connect_marks_connected(self) -> None:
        f = FakeMT5()
        f.connect()
        assert f.is_connected()

    def test_disconnect_marks_disconnected(self) -> None:
        f = FakeMT5()
        f.connect()
        f.disconnect()
        assert not f.is_connected()

    def test_order_send_raises_when_disconnected(self) -> None:
        f = FakeMT5()
        with pytest.raises(V17GatewayDisconnected):
            f.order_send(_order())


class TestFakeMT5Tick:
    def test_tick_returns_none_when_absent(self) -> None:
        f = FakeMT5()
        f.connect()
        assert f.tick(Symbol("EURUSD")) is None

    def test_tick_returns_set_value(self) -> None:
        f = FakeMT5()
        f.connect()
        t = _tick()
        f.set_tick(Symbol("EURUSD"), t)
        assert f.tick(Symbol("EURUSD")) == t


class TestFakeMT5Rates:
    def test_rates_empty_when_unset(self) -> None:
        f = FakeMT5()
        f.connect()
        assert f.rates(Symbol("EURUSD"), TF.M1, 10) == []

    def test_rates_returns_last_n(self) -> None:
        f = FakeMT5()
        f.connect()
        bars = [_bar(i) for i in range(5)]
        f.set_bars(Symbol("EURUSD"), TF.M1, bars)
        result = f.rates(Symbol("EURUSD"), TF.M1, 3)
        assert result == bars[-3:]

    def test_rates_count_exceeds_available(self) -> None:
        f = FakeMT5()
        f.connect()
        bars = [_bar(i) for i in range(2)]
        f.set_bars(Symbol("EURUSD"), TF.M1, bars)
        assert f.rates(Symbol("EURUSD"), TF.M1, 10) == bars


class TestFakeMT5OrderSend:
    def test_buy_fills_at_ask(self) -> None:
        f = FakeMT5()
        f.connect()
        f.set_tick(Symbol("EURUSD"), _tick("1.10000", "1.10008"))
        result = f.order_send(_order(Side.BUY))
        assert result.ok
        assert result.ticket is not None
        assert result.filled_price == Decimal("1.10008")

    def test_sell_fills_at_bid(self) -> None:
        f = FakeMT5()
        f.connect()
        f.set_tick(Symbol("EURUSD"), _tick("1.10000", "1.10008"))
        result = f.order_send(_order(Side.SELL))
        assert result.ok
        assert result.filled_price == Decimal("1.10000")

    def test_order_without_tick_fails(self) -> None:
        f = FakeMT5()
        f.connect()
        result = f.order_send(_order())
        assert not result.ok
        assert result.error_code == 1

    def test_tickets_are_unique(self) -> None:
        f = FakeMT5()
        f.connect()
        f.set_tick(Symbol("EURUSD"), _tick())
        r1 = f.order_send(_order(Side.BUY))
        r2 = f.order_send(_order(Side.SELL))
        assert r1.ticket != r2.ticket


class TestFakeMT5Modify:
    def test_modify_updates_sl_tp(self) -> None:
        f = FakeMT5()
        f.connect()
        f.set_tick(Symbol("EURUSD"), _tick())
        r = f.order_send(_order())
        ticket = r.ticket
        assert ticket is not None
        new_sl, new_tp = Decimal("1.09800"), Decimal("1.10300")
        result = f.order_modify(ticket, new_sl, new_tp)
        assert result.ok
        pos = next(p for p in f.positions() if p.ticket == ticket)
        assert pos.sl == new_sl
        assert pos.tp == new_tp

    def test_modify_unknown_ticket_fails(self) -> None:
        f = FakeMT5()
        f.connect()
        result = f.order_modify(Ticket(999), Decimal("1.09"), Decimal("1.11"))
        assert not result.ok
        assert result.error_code == 2


class TestFakeMT5Close:
    def test_close_removes_position(self) -> None:
        f = FakeMT5()
        f.connect()
        f.set_tick(Symbol("EURUSD"), _tick())
        r = f.order_send(_order())
        ticket = r.ticket
        assert ticket is not None
        assert len(f.positions()) == 1
        result = f.order_close(ticket)
        assert result.ok
        assert len(f.positions()) == 0

    def test_close_unknown_ticket_fails(self) -> None:
        f = FakeMT5()
        f.connect()
        result = f.order_close(Ticket(999))
        assert not result.ok
        assert result.error_code == 2


class TestFakeMT5Positions:
    def test_positions_empty_initially(self) -> None:
        f = FakeMT5()
        f.connect()
        assert f.positions() == []

    def test_positions_returns_open_trades(self) -> None:
        f = FakeMT5()
        f.connect()
        f.set_tick(Symbol("EURUSD"), _tick())
        f.order_send(_order(Side.BUY))
        f.order_send(_order(Side.SELL))
        assert len(f.positions()) == 2

    def test_symbol_select_no_op(self) -> None:
        f = FakeMT5()
        f.symbol_select(Symbol("EURUSD"))  # must not raise


class TestFakeMT5IsTradeGateway:
    def test_structural_subtype(self) -> None:
        from v17.mt5.protocol import TradeGateway
        f = FakeMT5()
        assert isinstance(f, TradeGateway)
