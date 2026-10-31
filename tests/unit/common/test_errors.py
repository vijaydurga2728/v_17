from v17.common.errors import (
    V17ConfigError,
    V17DataError,
    V17Error,
    V17FTMORuleViolation,
    V17GatewayDisconnected,
    V17GatewayError,
    V17KillSwitchActive,
    V17StructureError,
    V17ValidationFailed,
)


def test_hierarchy() -> None:
    assert issubclass(V17GatewayDisconnected, V17GatewayError)
    for e in (
        V17ConfigError,
        V17DataError,
        V17StructureError,
        V17GatewayError,
        V17ValidationFailed,
        V17KillSwitchActive,
        V17FTMORuleViolation,
    ):
        assert issubclass(e, V17Error)


def test_context_kwargs() -> None:
    err = V17DataError("bad row", symbol="EURUSD", row=42)
    assert err.ctx == {"symbol": "EURUSD", "row": 42}
    assert "bad row" in str(err)
