from __future__ import annotations

import tempfile
from pathlib import Path

import markdown2


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

    html = markdown2.markdown(markdown)
    full_html = _wrap_html(html)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.png"
        try:
            imgkit.from_string(full_html, str(output_path))
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
