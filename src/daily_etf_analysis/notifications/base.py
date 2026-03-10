from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class NotificationResult:
    sent: bool
    reason: str


@dataclass(slots=True)
class NotificationDispatchResult:
    sent: bool
    reason: str
    channel_results: dict[str, NotificationResult] = field(default_factory=dict)


class NotificationChannel(Protocol):
    channel: str

    def is_enabled(self) -> bool: ...

    def send_markdown(self, title: str, markdown: str) -> NotificationResult: ...
