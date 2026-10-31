from __future__ import annotations

from v17.mt5.protocol import TradeGateway


def test_protocol_has_required_methods() -> None:
    required = {
        "connect",
        "disconnect",
        "symbol_select",
        "tick",
        "rates",
        "order_send",
        "order_modify",
        "order_close",
        "positions",
    }
    for name in required:
        assert hasattr(TradeGateway, name), f"TradeGateway missing method: {name}"
