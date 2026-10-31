from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from v17.common.clock import FrozenClock
from v17.live.kill_switch import read_kill
from v17.obs.bot import TelegramCommandBot


_NOW = datetime(2026, 1, 6, 7, 30, tzinfo=UTC)
_CLOCK = FrozenClock(_NOW)


def _bot(tmp_path: Path) -> TelegramCommandBot:
    rg = MagicMock()
    rg.daily_markdown.return_value = "# Report"
    return TelegramCommandBot(
        token="tok",
        chat_id="99",
        state_root=tmp_path,
        report_generator=rg,
        clock=_CLOCK,
    )


class TestBotKillCommand:
    def test_kill_writes_sentinel(self, tmp_path: Path) -> None:
        bot = _bot(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        bot._handle_command("/kill", "99")
        assert read_kill(tmp_path)

    def test_kill_replies(self, tmp_path: Path) -> None:
        bot = _bot(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        with patch.object(bot, "_send_message") as mock_send:
            bot._handle_command("/kill", "99")
            mock_send.assert_called_once()
            assert "KILL" in mock_send.call_args[0][0]


class TestBotIgnoreOtherChat:
    def test_ignores_unknown_chat(self, tmp_path: Path) -> None:
        bot = _bot(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        with patch.object(bot, "_send_message") as mock_send:
            bot._handle_command("/kill", "ATTACKER_CHAT")
            mock_send.assert_not_called()
        assert not read_kill(tmp_path)


class TestBotStatusCommand:
    def test_status_no_runner(self, tmp_path: Path) -> None:
        bot = _bot(tmp_path)
        with patch.object(bot, "_send_message") as mock_send:
            bot._handle_command("/status", "99")
            mock_send.assert_called_once()
            assert "runner" in mock_send.call_args[0][0].lower()

    def test_status_with_runner(self, tmp_path: Path) -> None:
        bot = _bot(tmp_path)
        runner = MagicMock()
        runner.state.value = "armed"
        bot.wire_runner(runner)
        with patch.object(bot, "_send_message") as mock_send:
            bot._handle_command("/status", "99")
            mock_send.assert_called_once()
            assert "armed" in mock_send.call_args[0][0].lower()


class TestBotPauseResume:
    def test_pause_creates_sentinel(self, tmp_path: Path) -> None:
        bot = _bot(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        bot._handle_command("/pause", "99")
        assert (tmp_path / "PAUSE").exists()

    def test_resume_removes_sentinel(self, tmp_path: Path) -> None:
        bot = _bot(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "PAUSE").touch()
        bot._handle_command("/resume", "99")
        assert not (tmp_path / "PAUSE").exists()


class TestBotSendMessage:
    def test_send_message_calls_post(self, tmp_path: Path) -> None:
        import httpx
        bot = _bot(tmp_path)
        with patch("v17.obs.bot.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            bot._send_message("hello")
            mock_post.assert_called_once()

    def test_send_message_network_error_does_not_raise(self, tmp_path: Path) -> None:
        bot = _bot(tmp_path)
        with patch("v17.obs.bot.httpx.post") as mock_post:
            mock_post.side_effect = Exception("down")
            bot._send_message("test")  # must not raise
