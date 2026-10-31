from __future__ import annotations

from decimal import Decimal

from v17.common.dtos import Bar, OrderRequest, OrderResult, Position, Tick
from v17.common.errors import V17GatewayDisconnected
from v17.common.types import TF, Side, Symbol, Ticket


class FakeMT5:
    """In-memory TradeGateway for tests. Not thread-safe."""

    def __init__(self) -> None:
        self._connected: bool = False
        self._ticks: dict[str, Tick] = {}
        self._bars: dict[tuple[str, str], list[Bar]] = {}
        self._positions: dict[int, Position] = {}
        self._next_ticket: int = 1

    # --- helpers ---

    def is_connected(self) -> bool:
        return self._connected

    def set_tick(self, symbol: Symbol, tick: Tick) -> None:
        self._ticks[str(symbol)] = tick

    def set_bars(self, symbol: Symbol, tf: TF, bars: list[Bar]) -> None:
        self._bars[(str(symbol), str(tf))] = list(bars)

    # --- TradeGateway interface ---

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def symbol_select(self, symbol: Symbol) -> None:
        pass

    def tick(self, symbol: Symbol) -> Tick | None:
        return self._ticks.get(str(symbol))

    def rates(self, symbol: Symbol, tf: TF, count: int) -> list[Bar]:
        bars = self._bars.get((str(symbol), str(tf)), [])
        return bars[-count:] if count < len(bars) else list(bars)

    def order_send(self, order: OrderRequest) -> OrderResult:
        if not self._connected:
            raise V17GatewayDisconnected("FakeMT5 not connected")
        t = self._ticks.get(str(order.symbol))
        if t is None:
            return OrderResult(ok=False, error_code=1, error_message="no tick for symbol")
        filled_price = t.ask if order.side == Side.BUY else t.bid
        ticket = Ticket(self._next_ticket)
        self._next_ticket += 1
        pos = Position(
            ticket=ticket,
            symbol=order.symbol,
            side=order.side,
            size_lots=order.size_lots,
            opened_at=t.ts,
            entry=filled_price,
            sl=order.sl,
            tp=order.tp,
            current_price=filled_price,
            unrealized_pnl=Decimal("0"),
        )
        self._positions[int(ticket)] = pos
        return OrderResult(ok=True, ticket=ticket, filled_price=filled_price, filled_at=t.ts)

    def order_modify(self, ticket: Ticket, sl: Decimal, tp: Decimal) -> OrderResult:
        raw = self._positions.get(int(ticket))
        if raw is None:
            return OrderResult(ok=False, error_code=2, error_message="position not found")
        updated = Position(
            ticket=raw.ticket,
            symbol=raw.symbol,
            side=raw.side,
            size_lots=raw.size_lots,
            opened_at=raw.opened_at,
            entry=raw.entry,
            sl=sl,
            tp=tp,
            current_price=raw.current_price,
            unrealized_pnl=raw.unrealized_pnl,
        )
        self._positions[int(ticket)] = updated
        return OrderResult(ok=True, ticket=ticket)

    def order_close(self, ticket: Ticket) -> OrderResult:
        if int(ticket) not in self._positions:
            return OrderResult(ok=False, error_code=2, error_message="position not found")
        del self._positions[int(ticket)]
        return OrderResult(ok=True, ticket=ticket)

    def positions(self) -> list[Position]:
        return list(self._positions.values())
