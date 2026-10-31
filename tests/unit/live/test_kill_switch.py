from __future__ import annotations
from pathlib import Path
import pytest
from v17.live.kill_switch import clear_kill, read_kill, write_kill


def test_no_sentinel_returns_false(tmp_path: Path) -> None:
    assert read_kill(tmp_path) is False


def test_write_then_read(tmp_path: Path) -> None:
    write_kill(tmp_path)
    assert read_kill(tmp_path) is True


def test_clear_removes_sentinel(tmp_path: Path) -> None:
    write_kill(tmp_path)
    clear_kill(tmp_path)
    assert read_kill(tmp_path) is False


def test_clear_idempotent_when_absent(tmp_path: Path) -> None:
    clear_kill(tmp_path)  # must not raise
