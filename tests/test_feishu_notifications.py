from __future__ import annotations

from daily_etf_analysis.config.settings import Settings
from daily_etf_analysis.notifications.feishu import FeishuNotifier


def test_feishu_notifier_disabled_without_webhook() -> None:
    notifier = FeishuNotifier(Settings(feishu_webhook_url=None))
    result = notifier.send_markdown(title="Daily ETF", markdown="hello")
    assert result.sent is False
    assert result.reason == "disabled"


def test_feishu_notifier_sends_payload(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

    def _post(url, json, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["payload"] = json
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("daily_etf_analysis.notifications.feishu.httpx.post", _post)

    notifier = FeishuNotifier(Settings(feishu_webhook_url="https://example.com/hook"))
    result = notifier.send_markdown(title="Daily ETF", markdown="summary")

    assert result.sent is True
    assert result.reason == "ok"
    assert captured["url"] == "https://example.com/hook"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["msg_type"] == "post"  # type: ignore[index]


def test_feishu_notifier_handles_post_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def _post(url, json, timeout):  # type: ignore[no-untyped-def]
        raise RuntimeError("network down")

    monkeypatch.setattr("daily_etf_analysis.notifications.feishu.httpx.post", _post)

    notifier = FeishuNotifier(Settings(feishu_webhook_url="https://example.com/hook"))
    result = notifier.send_markdown(title="Daily ETF", markdown="summary")

    assert result.sent is False
    assert "network down" in result.reason
