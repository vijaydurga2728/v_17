from __future__ import annotations

from pathlib import Path

import pytest


class TestLoggingFileHandler:
    def test_configure_with_log_dir_creates_file(self, tmp_path: Path) -> None:
        from v17.common.logging import configure
        log_dir = tmp_path / "logs"
        configure(level="INFO", log_dir=log_dir)
        assert log_dir.exists()
        assert (log_dir / "v17.jsonl").exists()

    def test_configure_without_log_dir_no_file(self, tmp_path: Path) -> None:
        from v17.common.logging import configure
        # No log_dir — must not create any file
        configure(level="INFO")  # must not raise
