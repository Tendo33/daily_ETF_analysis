from __future__ import annotations

import logging
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
                continue
            if not notifier.is_enabled():
                channel_results[channel] = NotificationResult(
                    sent=False, reason="disabled"
                )
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
                        channel_results[channel] = send_image(
                            title, image_bytes, filename="daily_etf_report.png"
                        )
                    else:
                        if image_bytes is None:
                            logging.getLogger(__name__).warning(
                                "Markdown-to-image skipped for channel=%s", channel
                            )
                        channel_results[channel] = notifier.send_markdown(
                            title, markdown
                        )
                else:
                    channel_results[channel] = notifier.send_markdown(title, markdown)
            except Exception as exc:  # noqa: BLE001
                channel_results[channel] = NotificationResult(
                    sent=False, reason=str(exc)
                )

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
