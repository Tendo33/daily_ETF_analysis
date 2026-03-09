from __future__ import annotations

from dataclasses import dataclass

import httpx

from daily_etf_analysis.config.settings import Settings, get_settings


@dataclass(slots=True)
class NotificationResult:
    sent: bool
    reason: str


class FeishuNotifier:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        webhook_url: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.settings = settings or get_settings()
        self.webhook_url = webhook_url or self.settings.feishu_webhook_url
        self.timeout_seconds = timeout_seconds

    def is_enabled(self) -> bool:
        return bool(self.webhook_url)

    def send_markdown(self, title: str, markdown: str) -> NotificationResult:
        if not self.webhook_url:
            return NotificationResult(sent=False, reason="disabled")

        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": [[{"tag": "text", "text": markdown}]],
                    }
                }
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
