from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from v17.common.clock import Clock
from v17.live.kill_switch import write_kill
from v17.obs.report import ReportGenerator

if TYPE_CHECKING:
    from v17.live.runner import LiveRunner

_log = structlog.get_logger(__name__)
_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramCommandBot:
    def __init__(
        self,
        token: str,
        chat_id: str,
        state_root: Path,
        report_generator: ReportGenerator,
        clock: Clock,
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._state_root = state_root
        self._report_generator = report_generator
        self._clock = clock
        self._runner: LiveRunner | None = None
        self._offset = 0
        self._running = False
        self._thread: threading.Thread | None = None

    def wire_runner(self, runner: LiveRunner) -> None:
        self._runner = runner

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="tg-bot")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _poll_loop(self) -> None:
        while self._running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._process_update(update)
                    self._offset = update.get("update_id", self._offset) + 1
            except Exception as exc:
                _log.warning("bot_poll_error", error=str(exc))
            time.sleep(2)

    def _get_updates(self) -> list[dict[str, Any]]:
        url = _BASE.format(token=self._token, method="getUpdates")
        resp = httpx.get(
            url,
            params={"offset": self._offset, "timeout": 10},
            timeout=15.0,
        )
        data = resp.json()
        return data.get("result", [])  # type: ignore[no-any-return]

    def _process_update(self, update: dict[str, Any]) -> None:
        msg = update.get("message", {})
        text = msg.get("text", "")
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if not text.startswith("/"):
            return
        command = text.split()[0]
        self._handle_command(command, chat_id)

    def _handle_command(self, command: str, chat_id: str) -> None:
        if chat_id != self._chat_id:
            _log.warning("bot_unauthorized_chat", chat_id=chat_id)
            return
        if command == "/status":
            if self._runner is None:
                self._send_message("No runner wired")
            else:
                self._send_message(f"Runner state: {self._runner.state.value}")
        elif command == "/kill":
            write_kill(self._state_root)
            self._send_message("KILL sentinel written — runner will go IDLE on next tick")
        elif command == "/pause":
            self._state_root.mkdir(parents=True, exist_ok=True)
            (self._state_root / "PAUSE").touch()
            self._send_message("PAUSE sentinel written")
        elif command == "/resume":
            p = self._state_root / "PAUSE"
            if p.exists():
                p.unlink()
            self._send_message("PAUSE sentinel cleared")
        elif command == "/report":
            from decimal import Decimal

            from v17.common.dtos import AccountState

            now = self._clock.now()
            date_str = now.strftime("%Y-%m-%d")
            account = AccountState(
                equity=Decimal("0"),
                balance=Decimal("0"),
                starting_equity=Decimal("100000"),
                peak_equity=Decimal("0"),
                daily_realized_pnl=Decimal("0"),
                total_realized_pnl=Decimal("0"),
                best_day_pnl=Decimal("0"),
                open_positions=0,
                trading_days_count=0,
                is_locked_today=False,
                kill_active=False,
            )
            if self._runner is not None:
                pass  # M10 will wire account from runner
            md = self._report_generator.daily_markdown(date_str, account)
            self._send_message(md[:4096])  # Telegram max message length
        else:
            self._send_message(
                f"Unknown command: {command}. Available: /status /kill /pause /resume /report"
            )

    def _send_message(self, text: str) -> None:
        url = _BASE.format(token=self._token, method="sendMessage")
        try:
            httpx.post(url, json={"chat_id": self._chat_id, "text": text}, timeout=5.0)
        except Exception as exc:
            _log.warning("bot_send_failed", error=str(exc))
