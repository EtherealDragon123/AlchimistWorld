"""Разметка описаний (FR-2.6).

Qt умеет Markdown сам (`QTextDocument.setMarkdown`), но описания короткие, а от
полноценного движка нужны только жирный, курсив и списки. Небольшой преобразователь
не тянет зависимостей и одинаково ведёт себя на всех платформах.
"""

from __future__ import annotations

import html
import re

_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)
_ITALIC = re.compile(
    r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", re.DOTALL
)
_CODE = re.compile(r"`([^`]+)`")
_LIST_ITEM = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED_ITEM = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def _inline(text: str) -> str:
    text = html.escape(text)
    text = _CODE.sub(r"<code>\1</code>", text)
    text = _BOLD.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)
    text = _ITALIC.sub(lambda m: f"<i>{m.group(1) or m.group(2)}</i>", text)
    return text


def to_html(markdown: str) -> str:
    """Жирный, курсив, код, заголовки, списки и абзацы."""
    if not markdown.strip():
        return ""
    html_lines: list[str] = []
    list_tag: str | None = None
    paragraph: list[str] = []

    def close_paragraph() -> None:
        if paragraph:
            html_lines.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            html_lines.append(f"</{list_tag}>")
            list_tag = None

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            close_paragraph()
            close_list()
            continue

        heading = _HEADING.match(line)
        if heading:
            close_paragraph()
            close_list()
            level = min(6, len(heading.group(1)) + 2)
            html_lines.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue

        item = _LIST_ITEM.match(line)
        ordered = _ORDERED_ITEM.match(line) if not item else None
        if item or ordered:
            close_paragraph()
            wanted = "ul" if item else "ol"
            if list_tag != wanted:
                close_list()
                list_tag = wanted
                html_lines.append(f"<{wanted}>")
            content = (item or ordered).group(1)
            html_lines.append(f"<li>{_inline(content)}</li>")
            continue

        close_list()
        paragraph.append(line.strip())

    close_paragraph()
    close_list()
    return "".join(html_lines)


def to_plain(markdown: str, limit: int = 160) -> str:
    """Короткая строка для подсказок и списков."""
    text = re.sub(r"[*_`#>]", "", markdown).strip()
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
