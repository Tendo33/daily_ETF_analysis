from __future__ import annotations

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.notifications.base import NotificationResult
from daily_etf_analysis.notifications.manager import NotificationManager


class _SuccessNotifier:
    channel = "mock_success"

    def is_enabled(self) -> bool:
        return True

    def send_markdown(self, title: str, markdown: str) -> NotificationResult:
        return NotificationResult(sent=True, reason="ok")


class _FailNotifier:
    channel = "mock_fail"

    def is_enabled(self) -> bool:
        return True

    def send_markdown(self, title: str, markdown: str) -> NotificationResult:
        return NotificationResult(sent=False, reason="network_error")


class _DisabledNotifier:
    channel = "mock_disabled"

    def is_enabled(self) -> bool:
        return False

    def send_markdown(self, title: str, markdown: str) -> NotificationResult:
        return NotificationResult(sent=False, reason="disabled")


class _ExceptionNotifier:
    channel = "mock_exception"

    def is_enabled(self) -> bool:
        return True

    def send_markdown(self, title: str, markdown: str) -> NotificationResult:
        raise RuntimeError("token=abc123 webhook=https://example.com/hook error")


class _SensitiveReasonNotifier:
    channel = "mock_sensitive_reason"

    def is_enabled(self) -> bool:
        return True

    def send_markdown(self, title: str, markdown: str) -> NotificationResult:
        return NotificationResult(
            sent=False,
            reason="delivery failed webhook=https://example.com/hook token=abc123",
        )


def test_notification_manager_aggregates_multi_channel_results() -> None:
    settings = Settings(notify_channels=["mock_success", "mock_fail"])
    manager = NotificationManager(
        settings=settings,
        notifiers={
            "mock_success": _SuccessNotifier(),
            "mock_fail": _FailNotifier(),
        },
    )

    result = manager.send_markdown("daily", "body")
    assert result.sent is True
    assert result.channel_results["mock_success"].sent is True
    assert result.channel_results["mock_fail"].sent is False


def test_notification_manager_non_blocking_failure() -> None:
    settings = Settings(notify_channels=["mock_fail", "mock_success"])
    manager = NotificationManager(
        settings=settings,
        notifiers={"mock_fail": _FailNotifier(), "mock_success": _SuccessNotifier()},
    )

    result = manager.send_markdown("daily", "body")
    assert result.sent is True
    assert result.reason == "ok"


def test_notification_manager_marks_disabled_channels() -> None:
    settings = Settings(notify_channels=["mock_disabled"])
    manager = NotificationManager(
        settings=settings,
        notifiers={"mock_disabled": _DisabledNotifier()},
    )

    result = manager.send_markdown("daily", "body")
    assert result.sent is False
    assert result.channel_results["mock_disabled"].reason == "disabled"


def test_notification_manager_empty_channels_are_disabled() -> None:
    settings = Settings(notify_channels=[])
    manager = NotificationManager(settings=settings, notifiers={})

    result = manager.send_markdown("daily", "body")
    assert result.sent is False
    assert result.reason == "disabled"
    assert result.channel_results == {}


def test_notification_manager_masks_sensitive_failure_reason() -> None:
    settings = Settings(notify_channels=["mock_exception"])
    manager = NotificationManager(
        settings=settings,
        notifiers={"mock_exception": _ExceptionNotifier()},
    )

    result = manager.send_markdown("daily", "body")
    assert result.sent is False
    reason = result.channel_results["mock_exception"].reason
    assert reason is not None
    assert "token=" not in reason.lower()
    assert "http" not in reason.lower()
    assert "***" in reason


def test_notification_manager_sanitizes_sensitive_reason_from_channel_result() -> None:
    settings = Settings(notify_channels=["mock_sensitive_reason"])
    manager = NotificationManager(
        settings=settings,
        notifiers={"mock_sensitive_reason": _SensitiveReasonNotifier()},
    )

    result = manager.send_markdown("daily", "body")
    assert result.sent is False
    reason = result.channel_results["mock_sensitive_reason"].reason
    assert "token=" not in reason.lower()
    assert "http" not in reason.lower()
    assert "***" in reason
