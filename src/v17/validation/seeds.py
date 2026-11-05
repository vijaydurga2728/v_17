"""Deterministic SHA-256 based MCPT permutation seeds (spec section 7.4)."""
from __future__ import annotations

import hashlib


def permutation_seed(engine_id: str, scheme_id: str, permutation_index: int) -> int:
    s = f"v17-mcpt|{engine_id}|{scheme_id}|{permutation_index}"
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") & 0x7FFFFFFFFFFFFFFF
