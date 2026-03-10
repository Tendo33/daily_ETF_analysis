from __future__ import annotations

import base64
import hashlib

import httpx

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.notifications.base import NotificationResult


class WechatNotifier:
    channel = "wechat"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        webhook_url: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.settings = settings or get_settings()
        self.webhook_url = webhook_url or self.settings.wechat_webhook_url
        self.timeout_seconds = timeout_seconds

    def is_enabled(self) -> bool:
        return bool(self.webhook_url)

    def send_markdown(self, title: str, markdown: str) -> NotificationResult:
        if not self.webhook_url:
            return NotificationResult(sent=False, reason="disabled")

        payload = {
            "msgtype": "markdown",
            "markdown": {"content": f"# {title}\n\n{markdown}"},
        }
        try:
            response = httpx.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return NotificationResult(sent=True, reason="ok")
        except Exception as exc:  # noqa: BLE001
            return NotificationResult(sent=False, reason=str(exc))

    def send_image(
        self, title: str, image_bytes: bytes, filename: str = "report.png"
    ) -> NotificationResult:
        if not self.webhook_url:
            return NotificationResult(sent=False, reason="disabled")

        payload = {
            "msgtype": "image",
            "image": {
                "base64": base64.b64encode(image_bytes).decode("utf-8"),
                "md5": hashlib.md5(image_bytes).hexdigest(),
            },
        }
        try:
            response = httpx.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return NotificationResult(sent=True, reason="ok")
        except Exception as exc:  # noqa: BLE001
            return NotificationResult(sent=False, reason=str(exc))
