from __future__ import annotations

import types

from daily_etf_analysis.notifications.markdown_image import markdown_to_png


def test_markdown_to_png_returns_none_on_imgkit_error(monkeypatch) -> None:
    fake_imgkit = types.SimpleNamespace()

    def boom(*_args, **_kwargs) -> None:
        raise RuntimeError("boom")

    fake_imgkit.from_string = boom
    monkeypatch.setitem(__import__("sys").modules, "imgkit", fake_imgkit)

    assert markdown_to_png("# Title") is None
