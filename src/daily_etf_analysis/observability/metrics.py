from __future__ import annotations

import threading
from collections import defaultdict

_LABEL_ORDER = {
    "api_requests_total": ("method", "path", "status"),
    "analysis_task_total": ("status",),
    "provider_calls_total": ("provider", "operation", "status"),
    "notification_delivery_total": ("channel", "status"),
    "scheduler_runs_total": ("market", "status"),
    "report_render_total": ("mode",),
    "md2img_total": ("channel", "status"),
}


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, dict[tuple[str, ...], int]] = defaultdict(dict)

    def inc(self, metric: str, labels: tuple[str, ...]) -> None:
        with self._lock:
            bucket = self._counters.setdefault(metric, {})
            bucket[labels] = bucket.get(labels, 0) + 1

    def export_text(self) -> str:
        lines: list[str] = []
        with self._lock:
            for metric in sorted(_LABEL_ORDER):
                lines.append(f"# TYPE {metric} counter")
                label_names = _LABEL_ORDER[metric]
                series = self._counters.get(metric, {})
                if not series:
                    lines.append(f"{metric} 0")
                    continue
                for labels, value in sorted(series.items()):
                    if label_names:
                        rendered = ",".join(
                            f'{name}="{_escape(value_item)}"'
                            for name, value_item in zip(
                                label_names, labels, strict=True
                            )
                        )
                        lines.append(f"{metric}{{{rendered}}} {value}")
                    else:
                        lines.append(f"{metric} {value}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._counters = defaultdict(dict)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


_REGISTRY = MetricsRegistry()


def reset_metrics() -> None:
    _REGISTRY.reset()


def render_metrics_text() -> str:
    return _REGISTRY.export_text()


def inc_api_request(method: str, path: str, status: int) -> None:
    _REGISTRY.inc("api_requests_total", (method.upper(), path, str(status)))


def inc_analysis_task(status: str) -> None:
    _REGISTRY.inc("analysis_task_total", (status.lower(),))


def inc_provider_call(provider: str, operation: str, status: str) -> None:
    _REGISTRY.inc(
        "provider_calls_total",
        (provider.lower(), operation.lower(), status.lower()),
    )


def inc_notification_delivery(channel: str, status: str) -> None:
    _REGISTRY.inc("notification_delivery_total", (channel.lower(), status.lower()))


def inc_scheduler_run(market: str, status: str) -> None:
    _REGISTRY.inc("scheduler_runs_total", (market.lower(), status.lower()))


def inc_report_render(mode: str) -> None:
    _REGISTRY.inc("report_render_total", (mode.lower(),))


def inc_md2img(channel: str, status: str) -> None:
    _REGISTRY.inc("md2img_total", (channel.lower(), status.lower()))
