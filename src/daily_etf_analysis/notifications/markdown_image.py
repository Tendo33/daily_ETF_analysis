from __future__ import annotations

import re
import tempfile
from pathlib import Path

import markdown2

_UNSAFE_URL_PATTERN = re.compile(r"(?i)(file://|javascript:|data:)")


def markdown_to_png(
    markdown: str,
    *,
    engine: str = "imgkit",
    max_chars: int = 15000,
) -> bytes | None:
    if not markdown:
        return None
    if len(markdown) > max_chars:
        return None
    if engine != "imgkit":
        return None
    try:
        import imgkit
    except Exception:
        return None

    safe_markdown = _UNSAFE_URL_PATTERN.sub("#", markdown)
    html = markdown2.markdown(safe_markdown, safe_mode="escape")
    full_html = _wrap_html(html)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.png"
        try:
            imgkit.from_string(
                full_html,
                str(output_path),
                options={
                    "disable-local-file-access": "",
                    "disable-javascript": "",
                    "load-error-handling": "ignore",
                    "load-media-error-handling": "ignore",
                },
            )
        except Exception:
            return None
        if not output_path.exists():
            return None
        return output_path.read_bytes()


def _wrap_html(content: str) -> str:
    return (
        "<html><head><meta charset='utf-8'>"
        "<style>"
        "body{font-family:Arial,Helvetica,sans-serif;padding:24px;"
        "line-height:1.6;color:#0f172a;background:#ffffff;}"
        "h1,h2,h3{color:#0f172a;}"
        "code{background:#f1f5f9;padding:2px 6px;border-radius:4px;}"
        "</style></head><body>"
        f"{content}"
        "</body></html>"
    )
