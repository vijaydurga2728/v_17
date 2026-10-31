from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from v17.common.types import Symbol


def _make_settings(tmp_path: Path):  # type: ignore[no-untyped-def]
    from v17.config import Settings
    s = Settings(
        project_root=tmp_path,
        data_root=tmp_path / "data",
        telegram_token="",
        telegram_chat_id="",
        starting_equity=Decimal("100000"),
    )
    s.ensure_dirs()
    return s


class TestBuildComponentsDryRun:
    def test_returns_runner(self, tmp_path: Path) -> None:
        s = _make_settings(tmp_path)
        from v17.live.cli import _build_components
        components = _build_components(s, dry_run=True)
        assert components.runner is not None

    def test_bot_is_none_without_token(self, tmp_path: Path) -> None:
        s = _make_settings(tmp_path)
        from v17.live.cli import _build_components
        components = _build_components(s, dry_run=True)
        assert components.bot is None

    def test_store_created(self, tmp_path: Path) -> None:
        s = _make_settings(tmp_path)
        from v17.live.cli import _build_components
        components = _build_components(s, dry_run=True)
        assert components.store is not None


class TestKillCommand:
    def test_kill_writes_sentinel(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner
        from v17.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["kill"], env={
            "V17_DATA_ROOT": str(tmp_path / "data"),
        })
        assert result.exit_code == 0
        assert (tmp_path / "data" / "state" / "KILL").exists()


class TestMontecarloCommand:
    def test_missing_run_fails(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner
        from v17.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["montecarlo", "--run", "nonexistent"], env={
            "V17_DATA_ROOT": str(tmp_path / "data"),
        })
        assert result.exit_code != 0


class TestReportCommand:
    def test_report_no_data(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner
        from v17.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["report", "--day", "2026-01-06"], env={
            "V17_DATA_ROOT": str(tmp_path / "data"),
        })
        assert result.exit_code == 0
        assert "2026-01-06" in result.output
