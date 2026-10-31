from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from concurrent.futures import Future
from datetime import UTC, datetime
from decimal import Decimal
from queue import Queue
from threading import Thread
from typing import Any, TypeVar, cast

from v17.common.dtos import Bar, OrderRequest, OrderResult, Position, Tick
from v17.common.errors import V17GatewayDisconnected, V17GatewayError
from v17.common.types import TF, Side, Symbol, Ticket

try:
    import MetaTrader5 as _mt5_default  # type: ignore[import-untyped]  # noqa: N813
except ImportError:
    _mt5_default = None

_T = TypeVar("_T")
_STOP = object()
_RECONNECT_DELAYS = [1, 2, 4]  # seconds; 3 attempts, max 7 s total


def _is_disconnect_error(mt5: Any) -> bool:  # noqa: ANN401
    code, _ = mt5.last_error()
    # MT5 connection-related error codes are negative and < -1
    return bool(code < -1)


_TF_MAP: dict[TF, int] = {
    TF.M1: 1,
    TF.M15: 15,
    TF.H1: 16385,
    TF.H4: 16388,
    TF.D1: 16408,
}


class _Cmd:
    __slots__ = ("fn", "future")

    def __init__(self, fn: Callable[[], Any]) -> None:
        self.fn = fn
        self.future: Future[Any] = Future()


class MT5Gateway:
    """Thread-confined MetaTrader5 gateway.

    All MT5 calls run on a single worker thread to satisfy MT5's
    thread-affinity requirement. Public methods are synchronous.
    """

    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        *,
        _mt5: Any = None,  # noqa: ANN401
    ) -> None:
        self._login = login
        self._password = password
        self._server = server
        self._mt5 = _mt5 if _mt5 is not None else _mt5_default
        self._queue: Queue[Any] = Queue()
        self._thread = Thread(target=self._worker, daemon=True, name="mt5-worker")
        self._thread.start()

    # ------------------------------------------------------------------ #
    # Internal worker                                                       #
    # ------------------------------------------------------------------ #

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            cmd: _Cmd = item
            last_exc: BaseException | None = None
            for _attempt, delay in enumerate([0, *_RECONNECT_DELAYS]):
                if delay > 0:
                    time.sleep(delay)
                    with contextlib.suppress(Exception):
                        self._mt5.initialize(
                            login=self._login,
                            password=self._password,
                            server=self._server,
                        )
                try:
                    cmd.future.set_result(cmd.fn())
                    last_exc = None
                    break
                except V17GatewayDisconnected as exc:
                    last_exc = exc
                except Exception as exc:
                    cmd.future.set_exception(exc)
                    last_exc = None
                    break
            if last_exc is not None:
                cmd.future.set_exception(last_exc)

    def _run(self, fn: Callable[[], _T]) -> _T:
        cmd = _Cmd(fn)
        self._queue.put(cmd)
        return cast(_T, cmd.future.result(timeout=30))

    def _check_mt5(self) -> Any:  # noqa: ANN401
        if self._mt5 is None:
            raise V17GatewayError("MetaTrader5 package not installed")
        return self._mt5

    # ------------------------------------------------------------------ #
    # TradeGateway interface                                                #
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        mt5 = self._check_mt5()

        def _connect() -> None:
            if not mt5.initialize(
                login=self._login,
                password=self._password,
                server=self._server,
            ):
                code, msg = mt5.last_error()
                raise V17GatewayError(f"MT5 initialize failed: {msg}", code=code)

        self._run(_connect)

    def disconnect(self) -> None:
        mt5 = self._check_mt5()

        def _shutdown() -> None:
            mt5.shutdown()

        self._run(_shutdown)

    def symbol_select(self, symbol: Symbol) -> None:
        mt5 = self._check_mt5()

        def _select() -> None:
            if not mt5.symbol_select(str(symbol), True):
                code, msg = mt5.last_error()
                raise V17GatewayError(f"symbol_select failed for {symbol}: {msg}", code=code)

        self._run(_select)

    def tick(self, symbol: Symbol) -> Tick | None:
        mt5 = self._check_mt5()

        def _tick() -> Tick | None:
            t = mt5.symbol_info_tick(str(symbol))
            if t is None:
                if _is_disconnect_error(mt5):
                    raise V17GatewayDisconnected("tick: MT5 disconnected")
                return None
            return Tick(
                symbol=symbol,
                ts=datetime.fromtimestamp(t.time, tz=UTC),
                bid=Decimal(str(round(t.bid, 8))),
                ask=Decimal(str(round(t.ask, 8))),
            )

        return self._run(_tick)

    def rates(self, symbol: Symbol, tf: TF, count: int) -> list[Bar]:
        mt5 = self._check_mt5()
        mt5_tf = _TF_MAP[tf]

        def _rates() -> list[Bar]:
            rows = mt5.copy_rates_from_pos(str(symbol), mt5_tf, 0, count)
            if rows is None:
                if _is_disconnect_error(mt5):
                    raise V17GatewayDisconnected("rates: MT5 disconnected")
                return []
            result: list[Bar] = []
            for r in rows:
                op = Decimal(str(round(r.open, 8)))
                hi = Decimal(str(round(r.high, 8)))
                lo = Decimal(str(round(r.low, 8)))
                cl = Decimal(str(round(r.close, 8)))
                # Bar requires low <= open/close <= high
                if not (lo <= op <= hi and lo <= cl <= hi):
                    continue
                result.append(
                    Bar(
                        symbol=symbol,
                        tf=tf,
                        ts=datetime.fromtimestamp(r.time, tz=UTC),
                        open=op,
                        high=hi,
                        low=lo,
                        close=cl,
                        volume=int(getattr(r, "tick_volume", 0)),
                        spread_pips=Decimal(str(getattr(r, "spread", 0))) / Decimal("10"),
                    )
                )
            return result

        return self._run(_rates)

    def order_send(self, order: OrderRequest) -> OrderResult:
        mt5 = self._check_mt5()

        def _send() -> OrderResult:
            if order.entry is not None:
                price = float(order.entry)
            else:
                t = mt5.symbol_info_tick(str(order.symbol))
                price = float(t.ask if order.side == Side.BUY else t.bid) if t else 0.0
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": str(order.symbol),
                "volume": float(order.size_lots),
                "type": mt5.ORDER_TYPE_BUY if order.side == Side.BUY else mt5.ORDER_TYPE_SELL,
                "price": price,
                "sl": float(order.sl),
                "tp": float(order.tp),
                "deviation": 10,
                "magic": order.magic,
                "comment": order.comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res is None:
                if _is_disconnect_error(mt5):
                    raise V17GatewayDisconnected("order_send: MT5 disconnected")
                code, msg = mt5.last_error()
                return OrderResult(ok=False, error_code=code, error_message=msg)
            if res.retcode != mt5.TRADE_RETCODE_DONE:
                return OrderResult(
                    ok=False,
                    error_code=res.retcode,
                    error_message=getattr(res, "comment", ""),
                )
            now = datetime.now(tz=UTC)
            return OrderResult(
                ok=True,
                ticket=Ticket(res.order),
                filled_price=Decimal(str(round(res.price, 8))),
                filled_at=now,
            )

        return self._run(_send)

    def order_modify(self, ticket: Ticket, sl: Decimal, tp: Decimal) -> OrderResult:
        mt5 = self._check_mt5()

        def _modify() -> OrderResult:
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": int(ticket),
                "sl": float(sl),
                "tp": float(tp),
            }
            res = mt5.order_send(request)
            if res is None:
                if _is_disconnect_error(mt5):
                    raise V17GatewayDisconnected("order_modify: MT5 disconnected")
                code, msg = mt5.last_error()
                return OrderResult(ok=False, error_code=code, error_message=msg)
            if res.retcode != mt5.TRADE_RETCODE_DONE:
                return OrderResult(
                    ok=False,
                    error_code=res.retcode,
                    error_message=getattr(res, "comment", ""),
                )
            return OrderResult(ok=True, ticket=ticket)

        return self._run(_modify)

    def order_close(self, ticket: Ticket) -> OrderResult:
        mt5 = self._check_mt5()

        def _close() -> OrderResult:
            pos_list = mt5.positions_get(ticket=int(ticket))
            if not pos_list:
                if _is_disconnect_error(mt5):
                    raise V17GatewayDisconnected("order_close: MT5 disconnected")
                return OrderResult(ok=False, error_code=2, error_message="position not found")
            pos = pos_list[0]
            close_type = (
                mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            )
            t = mt5.symbol_info_tick(pos.symbol)
            close_price = (
                (t.bid if close_type == mt5.ORDER_TYPE_SELL else t.ask) if t else 0.0
            )
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": int(ticket),
                "price": close_price,
                "deviation": 10,
                "magic": 170000,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res is None:
                if _is_disconnect_error(mt5):
                    raise V17GatewayDisconnected("order_close send: MT5 disconnected")
                code, msg = mt5.last_error()
                return OrderResult(ok=False, error_code=code, error_message=msg)
            if res.retcode != mt5.TRADE_RETCODE_DONE:
                return OrderResult(
                    ok=False,
                    error_code=res.retcode,
                    error_message=getattr(res, "comment", ""),
                )
            return OrderResult(ok=True, ticket=ticket)

        return self._run(_close)

    def positions(self) -> list[Position]:
        mt5 = self._check_mt5()

        def _positions() -> list[Position]:
            raw = mt5.positions_get()
            if not raw:
                if _is_disconnect_error(mt5):
                    raise V17GatewayDisconnected("positions: MT5 disconnected")
                return []
            result: list[Position] = []
            for p in raw:
                side = Side.BUY if p.type == mt5.ORDER_TYPE_BUY else Side.SELL
                result.append(
                    Position(
                        ticket=Ticket(p.ticket),
                        symbol=Symbol(p.symbol),
                        side=side,
                        size_lots=Decimal(str(p.volume)),
                        opened_at=datetime.fromtimestamp(p.time, tz=UTC),
                        entry=Decimal(str(round(p.price_open, 8))),
                        sl=Decimal(str(round(p.sl, 8))),
                        tp=Decimal(str(round(p.tp, 8))),
                        current_price=Decimal(str(round(p.price_open, 8))),
                        unrealized_pnl=Decimal(str(round(p.profit, 2))),
                    )
                )
            return result

        return self._run(_positions)

    # ------------------------------------------------------------------ #
    # Context manager support                                               #
    # ------------------------------------------------------------------ #

    def __enter__(self) -> MT5Gateway:
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.disconnect()
        self._queue.put(_STOP)
        self._thread.join(timeout=5)
