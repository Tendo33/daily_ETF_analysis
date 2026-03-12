from __future__ import annotations

import logging
import time

import httpx

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.notifications.base import NotificationResult
from daily_etf_analysis.notifications.formatters import (
    chunk_content_by_max_bytes,
    format_feishu_markdown,
)

logger = logging.getLogger(__name__)


class FeishuNotifier:
    channel = "feishu"

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

        formatted_content = format_feishu_markdown(markdown)
        max_bytes = int(self.settings.feishu_max_bytes)
        content_bytes = len(formatted_content.encode("utf-8"))
        if content_bytes > max_bytes:
            chunks = chunk_content_by_max_bytes(
                formatted_content, max_bytes, add_page_marker=True
            )
        else:
            chunks = [formatted_content]

        success = True
        for idx, chunk in enumerate(chunks):
            if not self._send_feishu_message(title, chunk):
                success = False
            if idx < len(chunks) - 1:
                time.sleep(1)

        return NotificationResult(sent=success, reason="ok" if success else "failed")

    def send_image(
        self, title: str, image_bytes: bytes, filename: str = "report.png"
    ) -> NotificationResult:
        return NotificationResult(sent=False, reason="not_supported")

    def _post_payload(self, payload: dict) -> bool:
        if not self.webhook_url:
            return False
        webhook_url = self.webhook_url
        try:
            response = httpx.post(
                webhook_url,
                json=payload,
                timeout=self.timeout_seconds,
                verify=self.settings.webhook_verify_ssl,
            )
            response.raise_for_status()
            data = response.json()
            code = data.get("code") if isinstance(data, dict) else None
            if code == 0:
                return True
            logger.warning("Feishu response error: %s", data)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("Feishu delivery failed: %s", exc)
            return False

    def _send_feishu_message(self, title: str, content: str) -> bool:
        card_payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": content},
                    }
                ],
            },
        }

        if self._post_payload(card_payload):
            return True

        text_payload = {"msg_type": "text", "content": {"text": content}}
        return self._post_payload(text_payload)
