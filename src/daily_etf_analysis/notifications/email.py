from __future__ import annotations

import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from daily_etf_analysis.config.settings import Settings, get_settings
from daily_etf_analysis.notifications.base import NotificationResult


class EmailNotifier:
    channel = "email"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def is_enabled(self) -> bool:
        return bool(
            self.settings.email_smtp_host
            and self.settings.email_from
            and self.settings.email_to
        )

    def send_markdown(self, title: str, markdown: str) -> NotificationResult:
        if not self.is_enabled():
            return NotificationResult(sent=False, reason="disabled")

        body = MIMEText(markdown, "plain", "utf-8")
        body["Subject"] = title
        body["From"] = str(self.settings.email_from)
        body["To"] = ", ".join(self.settings.email_to)

        try:
            with smtplib.SMTP(
                str(self.settings.email_smtp_host), self.settings.email_smtp_port
            ) as smtp:
                if self.settings.email_username and self.settings.email_password:
                    smtp.login(
                        self.settings.email_username, self.settings.email_password
                    )
                smtp.sendmail(
                    str(self.settings.email_from),
                    list(self.settings.email_to),
                    body.as_string(),
                )
            return NotificationResult(sent=True, reason="ok")
        except Exception as exc:  # noqa: BLE001
            return NotificationResult(sent=False, reason=str(exc))

    def send_image(
        self, title: str, image_bytes: bytes, filename: str = "report.png"
    ) -> NotificationResult:
        if not self.is_enabled():
            return NotificationResult(sent=False, reason="disabled")

        message = MIMEMultipart()
        message["Subject"] = title
        message["From"] = str(self.settings.email_from)
        message["To"] = ", ".join(self.settings.email_to)
        message.attach(MIMEText("See attached report image.", "plain", "utf-8"))

        image_part = MIMEImage(image_bytes, name=filename)
        message.attach(image_part)

        try:
            with smtplib.SMTP(
                str(self.settings.email_smtp_host), self.settings.email_smtp_port
            ) as smtp:
                if self.settings.email_username and self.settings.email_password:
                    smtp.login(
                        self.settings.email_username, self.settings.email_password
                    )
                smtp.sendmail(
                    str(self.settings.email_from),
                    list(self.settings.email_to),
                    message.as_string(),
                )
            return NotificationResult(sent=True, reason="ok")
        except Exception as exc:  # noqa: BLE001
            return NotificationResult(sent=False, reason=str(exc))
