from __future__ import annotations

import logging
import re
from collections.abc import Mapping

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.notifications.base import (
    NotificationChannel,
    NotificationDispatchResult,
    NotificationResult,
)
from daily_etf_analysis.notifications.email import EmailNotifier
from daily_etf_analysis.notifications.feishu import FeishuNotifier
from daily_etf_analysis.notifications.markdown_image import markdown_to_png
from daily_etf_analysis.notifications.telegram import TelegramNotifier
from daily_etf_analysis.notifications.wechat import WechatNotifier
from daily_etf_analysis.observability.metrics import (
    inc_md2img,
    inc_notification_delivery,
)

_SENSITIVE_REASON_PATTERN = re.compile(
    r"(?i)(https?://\S+|sk-[a-z0-9_\-]+|token[=:]\S+|api[_-]?key[=:]\S+)"
)


class NotificationManager:
    def __init__(
        self,
        settings: Settings | None = None,
        notifiers: Mapping[str, NotificationChannel] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if notifiers is None:
            self.notifiers: dict[str, NotificationChannel] = {
                "feishu": FeishuNotifier(self.settings),
                "wechat": WechatNotifier(self.settings),
                "telegram": TelegramNotifier(self.settings),
                "email": EmailNotifier(self.settings),
            }
        else:
            self.notifiers = {str(k).lower(): v for k, v in notifiers.items()}

    def send_markdown(self, title: str, markdown: str) -> NotificationDispatchResult:
        selected_channels = [item.lower() for item in self.settings.notify_channels]
        image_channels = {
            item.lower() for item in self.settings.markdown_to_image_channels
        }
        channel_results: dict[str, NotificationResult] = {}

        for channel in selected_channels:
            notifier = self.notifiers.get(channel)
            if notifier is None:
                channel_results[channel] = NotificationResult(
                    sent=False, reason="disabled"
                )
                inc_notification_delivery(channel, "disabled")
                continue
            if not notifier.is_enabled():
                channel_results[channel] = NotificationResult(
                    sent=False, reason="disabled"
                )
                inc_notification_delivery(channel, "disabled")
                continue
            try:
                if channel in image_channels:
                    image_bytes = markdown_to_png(
                        markdown,
                        engine=self.settings.md2img_engine,
                        max_chars=self.settings.markdown_to_image_max_chars,
                    )
                    send_image = getattr(notifier, "send_image", None)
                    if image_bytes and callable(send_image):
                        raw_result = send_image(
                            title, image_bytes, filename="daily_etf_report.png"
                        )
                        channel_results[channel] = _sanitize_notification_result(
                            raw_result
                        )
                        if channel_results[channel].sent:
                            inc_md2img(channel, "success")
                        else:
                            inc_md2img(channel, "failed")
                    else:
                        if image_bytes is None:
                            logging.getLogger(__name__).warning(
                                "Markdown-to-image skipped for channel=%s", channel
                            )
                            inc_md2img(channel, "failed")
                        raw_result = notifier.send_markdown(title, markdown)
                        channel_results[channel] = _sanitize_notification_result(
                            raw_result
                        )
                else:
                    raw_result = notifier.send_markdown(title, markdown)
                    channel_results[channel] = _sanitize_notification_result(raw_result)
            except Exception as exc:  # noqa: BLE001
                channel_results[channel] = NotificationResult(
                    sent=False, reason=_sanitize_reason(exc)
                )
            delivery_status = "success" if channel_results[channel].sent else "failed"
            if channel_results[channel].reason == "disabled":
                delivery_status = "disabled"
            inc_notification_delivery(channel, delivery_status)

        if not channel_results:
            sent = False
            reason = "disabled"
        else:
            sent = any(item.sent for item in channel_results.values())
            if sent:
                reason = "ok"
            elif all(item.reason == "disabled" for item in channel_results.values()):
                reason = "disabled"
            else:
                reason = "failed"

        return NotificationDispatchResult(
            sent=sent,
            reason=reason,
            channel_results=channel_results,
        )


def _sanitize_reason(value: object) -> str:
    text = str(value).strip()
    if not text:
        return "unknown"
    masked = _SENSITIVE_REASON_PATTERN.sub("***", text)
    return masked[:200]


def _sanitize_notification_result(result: NotificationResult) -> NotificationResult:
    return NotificationResult(sent=result.sent, reason=_sanitize_reason(result.reason))
