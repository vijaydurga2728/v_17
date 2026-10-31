from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from v17.obs.alerter import TelegramAlerter


class TestTelegramAlerterSend:
    def test_send_calls_post(self) -> None:
        with patch("v17.obs.alerter.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            alerter = TelegramAlerter(token="tok123", chat_id="456")
            alerter.send("hello", level="info")
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            assert "sendMessage" in str(call_kwargs)

    def test_send_includes_level_in_text(self) -> None:
        with patch("v17.obs.alerter.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            alerter = TelegramAlerter(token="tok123", chat_id="456")
            alerter.send("entry fired", level="info")
            call_kwargs = mock_post.call_args
            body = call_kwargs.kwargs.get("json", call_kwargs[1].get("json", {}))
            assert "entry fired" in body.get("text", "")

    def test_send_network_error_does_not_raise(self) -> None:
        with patch("v17.obs.alerter.httpx.post") as mock_post:
            mock_post.side_effect = Exception("network down")
            alerter = TelegramAlerter(token="tok", chat_id="1")
            alerter.send("test")  # must not raise

    def test_implements_alerter_protocol(self) -> None:
        from v17.live.alerter import Alerter
        alerter = TelegramAlerter(token="tok", chat_id="1")
        assert isinstance(alerter, Alerter)
