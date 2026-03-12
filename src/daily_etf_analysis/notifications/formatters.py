from __future__ import annotations

import re

TRUNCATION_SUFFIX = "\n\n...(本段内容过长已截断)"
PAGE_MARKER_PREFIX = "\n\n📄"
PAGE_MARKER_SAFE_BYTES = 16
MIN_MAX_BYTES = 40


def _page_marker(i: int, total: int) -> str:
    return f"{PAGE_MARKER_PREFIX} {i + 1}/{total}"


def _bytes(s: str) -> int:
    return len(s.encode("utf-8"))


def _chunk_by_separators(content: str) -> tuple[list[str], str]:
    separators = ["\n---\n", "\n## ", "\n### ", "\n\n"]
    for sep in separators:
        if sep in content:
            return content.split(sep), sep
    return [content], ""


def _chunk_by_max_bytes(content: str, max_bytes: int) -> list[str]:
    sections: list[str] = []
    while True:
        chunk, content = slice_at_max_bytes(content, max_bytes)
        if content.strip() != "":
            sections.append(chunk + TRUNCATION_SUFFIX)
        else:
            sections.append(chunk)
            break
    return sections


def slice_at_max_bytes(text: str, max_bytes: int) -> tuple[str, str]:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, ""
    truncated = encoded[:max_bytes]
    while truncated and (truncated[-1] & 0xC0) == 0x80:
        truncated = truncated[:-1]
    truncated_text = truncated.decode("utf-8", errors="ignore")
    return truncated_text, text[len(truncated_text) :]


def chunk_content_by_max_bytes(
    content: str, max_bytes: int, add_page_marker: bool = False
) -> list[str]:
    def _chunk(content: str, max_bytes: int) -> list[str]:
        if max_bytes < MIN_MAX_BYTES:
            raise ValueError(f"max_bytes={max_bytes} < {MIN_MAX_BYTES}")
        if _bytes(content) <= max_bytes:
            return [content]
        sections, separator = _chunk_by_separators(content)
        if separator == "" and len(sections) == 1:
            return _chunk_by_max_bytes(content, max_bytes)

        chunks: list[str] = []
        current_chunk: list[str] = []
        current_bytes = 0
        separator_bytes = _bytes(separator) if separator else 0
        effective_max_bytes = max_bytes - separator_bytes

        for section in sections:
            section += separator
            section_bytes = _bytes(section)
            if section_bytes > effective_max_bytes:
                if current_chunk:
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_bytes = 0
                section_chunks = _chunk(section[:-separator_bytes], effective_max_bytes)
                section_chunks[-1] = section_chunks[-1] + separator
                chunks.extend(section_chunks)
                continue
            if current_bytes + section_bytes > effective_max_bytes:
                if current_chunk:
                    chunks.append("".join(current_chunk))
                current_chunk = [section]
                current_bytes = section_bytes
            else:
                current_chunk.append(section)
                current_bytes += section_bytes

        if current_chunk:
            chunks.append("".join(current_chunk))
        if (
            chunks
            and len(chunks[-1]) > separator_bytes
            and chunks[-1][-separator_bytes:] == separator
        ):
            chunks[-1] = chunks[-1][:-separator_bytes]
        return chunks

    if add_page_marker:
        max_bytes = max_bytes - PAGE_MARKER_SAFE_BYTES

    chunks = _chunk(content, max_bytes)
    if add_page_marker:
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            chunks[i] = chunk + _page_marker(i, total_chunks)
    return chunks


def format_feishu_markdown(content: str) -> str:
    def _flush_table_rows(buffer: list[str], output: list[str]) -> None:
        if not buffer:
            return

        def _parse_row(row: str) -> list[str]:
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            return [c for c in cells if c]

        rows = []
        for raw in buffer:
            if re.match(r"^\s*\|?\s*[:-]+\s*(\|\s*[:-]+\s*)+\|?\s*$", raw):
                continue
            parsed = _parse_row(raw)
            if parsed:
                rows.append(parsed)

        if not rows:
            return

        header = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else []
        for row in data_rows:
            pairs = []
            for idx, cell in enumerate(row):
                key = header[idx] if idx < len(header) else f"列{idx + 1}"
                pairs.append(f"{key}：{cell}")
            output.append(f"• {' | '.join(pairs)}")

    lines: list[str] = []
    table_buffer: list[str] = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip()

        if line.strip().startswith("|") and line.strip().endswith("|"):
            table_buffer.append(line)
            continue

        if table_buffer:
            _flush_table_rows(table_buffer, lines)
            table_buffer = []

        if line.startswith("# "):
            lines.append(f"**{line[2:].strip()}**")
        elif line.startswith("## "):
            lines.append(f"**{line[3:].strip()}**")
        elif line.startswith("### "):
            lines.append(f"**{line[4:].strip()}**")
        elif line.startswith("> "):
            lines.append(f"💬 {line[2:].strip()}")
        elif line.strip() == "---":
            lines.append("——")
        else:
            lines.append(line)

    if table_buffer:
        _flush_table_rows(table_buffer, lines)

    return "\n".join(lines).strip()
