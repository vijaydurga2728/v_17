from __future__ import annotations

import hashlib
from datetime import datetime

from v17.common.types import Side, SignalId, Symbol


def make_signal_id(symbol: Symbol, setup: str, at: datetime, side: Side) -> SignalId:
    raw = f"{symbol}:{setup}:{at.isoformat()}:{side.value}".encode()
    return SignalId(hashlib.sha1(raw).hexdigest()[:16])
