from __future__ import annotations

from pathlib import Path

_SENTINEL = "KILL"


def read_kill(state_root: Path) -> bool:
    return (state_root / _SENTINEL).exists()


def write_kill(state_root: Path) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / _SENTINEL).touch()


def clear_kill(state_root: Path) -> None:
    p = state_root / _SENTINEL
    if p.exists():
        p.unlink()
