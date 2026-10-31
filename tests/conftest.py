from __future__ import annotations

from pathlib import Path

import pytest

from v17.config import Settings


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Settings:
    s = Settings(project_root=tmp_path)
    s.ensure_dirs()
    return s
