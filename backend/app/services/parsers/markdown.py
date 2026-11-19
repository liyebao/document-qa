import re
from pathlib import Path

from app.services.parsers.base import ParseError, TextBlock, normalize_text

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")


def parse_markdown(data: bytes | Path) -> list[TextBlock]:
    raw = data if isinstance(data, bytes) else data.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError as exc:
            raise ParseError("Markdown 文件编码无法识别，请使用 UTF-8") from exc

    blocks: list[TextBlock] = []
    heading_stack: list[tuple[int, str]] = []
    paragraph: list[str] = []
    in_fence = False

    def flush() -> None:
        nonlocal paragraph
        content = normalize_text("\n".join(paragraph))
        if content:
            heading_path = " > ".join(title for _, title in heading_stack)
            blocks.append(TextBlock(text=content, heading_path=heading_path))
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

    if not blocks:
        raise ParseError("未从 Markdown 中提取到文本内容")
    return blocks
