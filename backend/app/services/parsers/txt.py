import re
from pathlib import Path

from app.services.parsers.base import ParseError, TextBlock, normalize_text

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def parse_txt(data: bytes | Path) -> list[TextBlock]:
    raw = data if isinstance(data, bytes) else data.read_bytes()
    text: str | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ParseError("TXT 文件编码无法识别，请使用 UTF-8")

    blocks: list[TextBlock] = []
    for paragraph in _PARAGRAPH_BREAK.split(text):
        content = normalize_text(paragraph)
        if content:
            blocks.append(TextBlock(text=content))

    if not blocks:
        raise ParseError("未从 TXT 中提取到文本内容")
    return blocks
