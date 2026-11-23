import re
from pathlib import Path

from app.services.parsers.base import ParseError, TextBlock, normalize_text

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")


def blocks_from_markdown_text(
    text: str, *, heading_prefix: str = ""
) -> list[TextBlock]:
    """把 Markdown 文本切成带标题路径的块。

    网页导入（trafilatura 输出 Markdown）和 EPUB 章节复用它，保证上传的
    Markdown、网页正文与 EPUB 三类来源的结构切分规则完全一致。
    """
    prefix = [item for item in heading_prefix.split(" > ") if item]
    blocks: list[TextBlock] = []
    heading_stack: list[tuple[int, str]] = []
    paragraph: list[str] = []
    in_fence = False

    def flush() -> None:
        nonlocal paragraph
        content = normalize_text("\n".join(paragraph))
        if content:
            parts = [*prefix, *(title for _, title in heading_stack)]
            blocks.append(
                TextBlock(
                    text=content,
                    heading_path=" > ".join(part for part in parts if part),
                )
            )
        paragraph = []

    for line in text.split("\n"):
        if _FENCE_PATTERN.match(line):
            paragraph.append(line)
            in_fence = not in_fence
            continue
        if in_fence:
            paragraph.append(line)
            continue
        heading = _HEADING_PATTERN.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            title = normalize_text(heading.group(2))
            heading_stack = [(lv, name) for lv, name in heading_stack if lv < level]
            heading_stack.append((level, title))
            continue
        if not line.strip():
            flush()
            continue
        paragraph.append(line)

    flush()
    return blocks


def parse_markdown(data: bytes | Path) -> list[TextBlock]:
    raw = data if isinstance(data, bytes) else data.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gb18030")
        except UnicodeDecodeError as exc:
            raise ParseError("Markdown 文件编码无法识别，请使用 UTF-8") from exc

    blocks = blocks_from_markdown_text(text)

    if not blocks:
        raise ParseError("未从 Markdown 中提取到文本内容")
    return blocks
