"""HTML 正文抽取的兜底实现（纯标准库）。

主路径复用 trafilatura——与网页导入 ``POST /collections/{id}/documents/url``
完全同一套参数，保证“上传 HTML”和“导入同一条链接”得到同一份正文。
但上传的 HTML 常常是片段、或正文被脚本包裹，trafilatura 可能返回空串；
这时用 HTMLParser 按块级元素切段、按 h1–h6 维护标题栈，至少保住可读正文，
而不是把整页标签或整段脚本原样入库。
"""

import re
from html.parser import HTMLParser

import trafilatura

from app.services.parsers.base import TextBlock, normalize_text

_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "head",
        "title",
        "template",
        "svg",
        "iframe",
        "object",
        "canvas",
    }
)
_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_CELL_TAGS = frozenset({"td", "th"})
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "li",
        "tr",
        "blockquote",
        "pre",
        "ul",
        "ol",
        "table",
        "body",
        "main",
        "header",
        "footer",
        "aside",
        "nav",
        "dl",
        "dt",
        "dd",
        "figure",
        "figcaption",
        "br",
        "hr",
        "form",
    }
)

_META_CHARSET = re.compile(rb"""charset\s*=\s*["']?([\w-]+)""", re.IGNORECASE)


def decode_html(raw: bytes) -> str:
    """按 BOM → meta charset → UTF-8 → GB18030 的顺序解码。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")

    candidates: list[str] = []
    declared = _META_CHARSET.search(raw[:4096])
    if declared:
        candidates.append(declared.group(1).decode("ascii", errors="ignore").lower())
    candidates.extend(("utf-8", "gb18030"))
    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


class _BlockExtractor(HTMLParser):
    def __init__(self, heading_prefix: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._heading_level = 0
        self._heading_text: list[str] = []
        self._buffer: list[str] = []
        self._stack: list[tuple[int, str]] = []
        self._cells_in_row = 0
        self._prefix = [item for item in heading_prefix.split(" > ") if item]
        self.blocks: list[TextBlock] = []

    def _flush(self) -> None:
        content = normalize_text("".join(self._buffer))
        self._buffer.clear()
        if not content:
            return
        parts = [*self._prefix, *(title for _, title in self._stack)]
        self.blocks.append(
            TextBlock(
                text=content,
                heading_path=" > ".join(part for part in parts if part),
            )
        )

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ARG002
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in _HEADING_TAGS:
            self._flush()
            self._heading_level = _HEADING_TAGS[tag]
            self._heading_text = []
            return
        if tag in _CELL_TAGS:
            if self._cells_in_row:
                self._buffer.append(" | ")
            self._cells_in_row += 1
            return
        if tag == "tr":
            self._flush()
            self._cells_in_row = 0
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._heading_level:
            self._heading_text.append(data)
            return
        self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in _HEADING_TAGS:
            title = normalize_text("".join(self._heading_text))
            self._heading_text = []
            level = self._heading_level
            self._heading_level = 0
            if not title:
                return
            self._stack = [(lv, name) for lv, name in self._stack if lv < level]
            self._stack.append((level, title))
            return
        if tag == "tr":
            # 行结束时才收尾：按单元格 flush 会把一行表格拆成「营收」「| 12%」
            # 多个块，列关系全丢。
            self._flush()
            self._cells_in_row = 0
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def close(self) -> None:
        super().close()
        self._flush()


def blocks_from_html(html: str, *, heading_prefix: str = "") -> list[TextBlock]:
    parser = _BlockExtractor(heading_prefix)
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001  HTMLParser 对畸形标记偶尔仍会抛出
        pass
    return parser.blocks


def extract_markdown(html: str) -> str:
    """trafilatura 抽正文为 Markdown，参数与网页导入保持一致；失败返回空串。"""
    try:
        return (
            trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                favor_recall=True,
                output_format="markdown",
            )
            or ""
        )
    except Exception:  # noqa: BLE001  抽取失败时由调用方退回块级兜底
        return ""
