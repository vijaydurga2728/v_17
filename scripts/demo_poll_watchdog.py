"""Demo poll watchdog (demo ADR 001).

Runs daily at 23:30 IST. Alerts if out/demo/last_poll.txt is older than
MAX_AGE_H hours, i.e. the 23:00 poll did not complete successfully.

Alert channel:
- Telegram, if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set in .env.
- Otherwise a Windows `msg` popup to the logged-on user.
Exit codes: 0 ok, 7 stale (alert sent), 8 stale and alert delivery failed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

MAX_AGE_H = 20.0


def poll_age_hours(last_poll: Path, now: datetime) -> float | None:
    if not last_poll.exists():
        return None
    ts = datetime.fromisoformat(last_poll.read_text(encoding="utf-8").strip())
    return (now - ts).total_seconds() / 3600.0


def _send_telegram(token: str, chat_id: str, text: str) -> None:
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode())
    if not body.get("ok"):
        raise RuntimeError("telegram API returned ok=false")


def _send_popup(text: str) -> None:
    subprocess.run(["msg", os.environ.get("USERNAME", "*"), text], check=True, timeout=15)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    try:
        from dotenv import load_dotenv
        load_dotenv(repo / ".env", override=True)
    except ImportError:
        pass

    age = poll_age_hours(repo / "out" / "forward_c14" / "last_poll.txt", datetime.now(UTC))
    if age is not None and age < MAX_AGE_H:
        print(f"[watchdog] ok, last poll {age:.1f}h ago")
        return 0

    text = (
        "RSI2 demo poll MISSED: "
        + ("no last_poll.txt" if age is None else f"last success {age:.1f}h ago")
        + ". Check MT5 is running and logged in; see Task Scheduler 'RSI2 Demo Poll'."
    )
    print(f"[watchdog] {text}")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    try:
        if token and chat_id:
            _send_telegram(token, chat_id, text)
        else:
            _send_popup(text)
    except Exception as exc:
        print(f"[watchdog] alert delivery failed: {type(exc).__name__}")
        return 8
    return 7


if __name__ == "__main__":
    sys.exit(main())
