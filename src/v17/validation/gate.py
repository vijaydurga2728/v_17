from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from v17.common.dtos import RunReport


class GateWriter:
    SENTINEL = "GATE_PASSED"

    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root

    @property
    def _path(self) -> Path:
        return self.state_root / self.SENTINEL

    def write_sentinel(self, report: RunReport, now: datetime | None = None) -> Path:
        self.state_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": str(report.run_id),
            "written_at": (now or datetime.now(UTC)).isoformat(),
            "report": report.model_dump(mode="json"),
        }
        self._path.write_text(json.dumps(payload, default=_json_default, indent=2))
        return self._path

    def revoke(self) -> bool:
        if self._path.exists():
            self._path.unlink()
            return True
        return False

    def is_active(self) -> bool:
        return self._path.exists()

    def read_active(self) -> dict[str, Any] | None:
        if not self.is_active():
            return None
        result: dict[str, Any] = json.loads(self._path.read_text())
        return result


def _json_default(x: object) -> object:
    if isinstance(x, Decimal):
        return float(x)
    iso = getattr(x, "isoformat", None)
    if callable(iso):
        result: object = iso()
        return result
    raise TypeError(f"not serializable: {type(x)}")
