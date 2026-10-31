from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from v17.common.clock import Clock
from v17.common.types import Symbol
from v17.data.ports import CalendarProvider
from v17.live.kill_switch import read_kill
from v17.mt5.protocol import TradeGateway

_GATE_FILE = "GATE_PASSED"


@dataclass(frozen=True)
class PreFlightResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


class PreFlight:
    def __init__(
        self,
        state_root: Path,
        gateway: TradeGateway,
        calendar: CalendarProvider,
        symbol: Symbol,
        clock: Clock,
    ) -> None:
        self._state_root = state_root
        self._gateway = gateway
        self._calendar = calendar
        self._symbol = symbol
        self._clock = clock

    def run(self) -> PreFlightResult:
        reasons: list[str] = []

        if not (self._state_root / _GATE_FILE).exists():
            reasons.append("GATE_PASSED sentinel missing — run 'v17 validate' first")

        if read_kill(self._state_root):
            reasons.append("KILL sentinel active — clear it before starting")

        try:
            t = self._gateway.tick(self._symbol)
            if t is None:
                reasons.append(f"MT5 tick returned None for {self._symbol}")
        except Exception as exc:
            reasons.append(f"MT5 tick failed: {exc}")

        try:
            now = self._clock.now()
            self._calendar.events(now, now)
        except Exception as exc:
            reasons.append(f"calendar not available: {exc}")

        return PreFlightResult(ok=len(reasons) == 0, reasons=reasons)
