from __future__ import annotations

import httpx
import structlog

_log = structlog.get_logger(__name__)

_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramAlerter:
    """Implements v17.live.alerter.Alerter via Telegram Bot API."""

    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = chat_id

    def send(self, message: str, level: str = "info") -> None:
        text = f"[{level.upper()}] {message}"
        url = _BASE.format(token=self._token, method="sendMessage")
        try:
            httpx.post(url, json={"chat_id": self._chat_id, "text": text}, timeout=5.0)
        except Exception as exc:
            _log.warning("telegram_send_failed", error=str(exc))
