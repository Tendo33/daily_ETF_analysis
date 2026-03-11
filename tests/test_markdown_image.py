from __future__ import annotations

import types
from pathlib import Path

from daily_etf_analysis.notifications.markdown_image import markdown_to_png


def test_markdown_to_png_returns_none_on_imgkit_error(monkeypatch) -> None:
    fake_imgkit = types.SimpleNamespace()

    def boom(*_args, **_kwargs) -> None:
        raise RuntimeError("boom")

    fake_imgkit.from_string = boom
    monkeypatch.setitem(__import__("sys").modules, "imgkit", fake_imgkit)

    assert markdown_to_png("# Title") is None


def test_markdown_to_png_sanitizes_unsafe_links(monkeypatch) -> None:
    captured: dict[str, object] = {}
    fake_imgkit = types.SimpleNamespace()

    def fake_render(html: str, output: str, options: dict[str, str]) -> None:
        captured["html"] = html
        captured["options"] = options
        Path(output).write_bytes(b"png")

    fake_imgkit.from_string = fake_render
    monkeypatch.setitem(__import__("sys").modules, "imgkit", fake_imgkit)

    data = markdown_to_png(
        "[x](javascript:alert(1)) ![img](file:///etc/passwd)\n[ok](https://example.com)"
    )
    assert data == b"png"
    html = str(captured["html"]).lower()
    assert "javascript:" not in html
    assert "file://" not in html
    options = captured["options"]
    assert isinstance(options, dict)
    assert "disable-local-file-access" in options
    assert "disable-javascript" in options
