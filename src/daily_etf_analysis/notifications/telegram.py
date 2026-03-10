from __future__ import annotations

import httpx

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.notifications.base import NotificationResult


class TelegramNotifier:
    channel = "telegram"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        bot_token: str | None = None,
        chat_id: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.settings = settings or get_settings()
        self.bot_token = bot_token or self.settings.telegram_bot_token
        self.chat_id = chat_id or self.settings.telegram_chat_id
        self.timeout_seconds = timeout_seconds

    def is_enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_markdown(self, title: str, markdown: str) -> NotificationResult:
        if not self.is_enabled():
            return NotificationResult(sent=False, reason="disabled")

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": f"{title}\n\n{markdown}",
            "disable_web_page_preview": True,
        }
        try:
            response = httpx.post(url, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            return NotificationResult(sent=True, reason="ok")
        except Exception as exc:  # noqa: BLE001
            return NotificationResult(sent=False, reason=str(exc))

    def send_image(
        self, title: str, image_bytes: bytes, filename: str = "report.png"
    ) -> NotificationResult:
        if not self.is_enabled():
            return NotificationResult(sent=False, reason="disabled")

        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        data = {"chat_id": self.chat_id, "caption": title}
        files = {"photo": (filename, image_bytes, "image/png")}
        try:
            response = httpx.post(
                url, data=data, files=files, timeout=self.timeout_seconds
            )
            response.raise_for_status()
            return NotificationResult(sent=True, reason="ok")
        except Exception as exc:  # noqa: BLE001
            return NotificationResult(sent=False, reason=str(exc))
