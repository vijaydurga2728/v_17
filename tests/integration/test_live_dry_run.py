from __future__ import annotations

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


class TestLiveDryRunSmoke:
    def test_build_components_assembles(self, tmp_path: Path) -> None:
        s = _make_settings(tmp_path)
        from v17.live.cli import _build_components
        c = _build_components(s, dry_run=True)
        assert c.runner is not None
        assert c.store is not None
        assert c.bot is None  # no token

    def test_runner_has_tick_poll(self, tmp_path: Path) -> None:
        s = _make_settings(tmp_path)
        from v17.live.cli import _build_components
        c = _build_components(s, dry_run=True)
        assert hasattr(c.runner, "_tick_poll")

    def test_store_survives_restart(self, tmp_path: Path) -> None:
        s = _make_settings(tmp_path)
        from v17.obs.store import TradeStore, create_engine_for_path
        engine = create_engine_for_path(s.db)
        store = TradeStore(engine)
        store.create_tables()
        store.record_equity("2026-01-06", store.load_account(s.starting_equity))
        # Reload from same path
        engine2 = create_engine_for_path(s.db)
        store2 = TradeStore(engine2)
        store2.create_tables()
        hist = store2.equity_history()
        assert len(hist) == 1

    def test_kill_command_and_dry_run_aware(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner
        from v17.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["kill"], env={
            "V17_DATA_ROOT": str(tmp_path / "data"),
        })
        assert result.exit_code == 0
        assert (tmp_path / "data" / "state" / "KILL").exists()

    def test_live_command_fails_without_gate(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner
        from v17.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["live"], env={
            "V17_DATA_ROOT": str(tmp_path / "data"),
        })
        assert result.exit_code != 0
        assert "GATE_PASSED" in result.output

    def test_paper_command_assembles_then_would_block(self, tmp_path: Path) -> None:
        # paper calls _build_components then runner.start() (blocking).
        # We can only test _build_components here.
        s = _make_settings(tmp_path)
        from v17.live.cli import _build_components
        c = _build_components(s, dry_run=True)
        assert c.runner is not None
