import re
from io import BytesIO
from pathlib import Path

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.parsers.base import ParseError, TextBlock, normalize_text

_HEADING_PATTERN = re.compile(r"^(heading|标题)\s*(\d+)$", re.IGNORECASE)


def _heading_level(style_name: str) -> int | None:
    if not style_name:
        return None
    match = _HEADING_PATTERN.match(style_name.strip())
    return int(match.group(2)) if match else None


def _table_to_text(table: Table) -> str:
    rows: list[str] = []
    for row in table.rows:
        cells = [normalize_text(cell.text) for cell in row.cells]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def parse_docx(data: bytes | Path) -> list[TextBlock]:
    try:
        document = DocxDocument(BytesIO(data) if isinstance(data, bytes) else data)
    except Exception as exc:  # noqa: BLE001
        raise ParseError("DOCX 文件损坏或格式不正确") from exc

    blocks: list[TextBlock] = []
    heading_stack: list[tuple[int, str]] = []

    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            text = normalize_text(paragraph.text)
            if not text:
                continue
            level = _heading_level(paragraph.style.name if paragraph.style else "")
            if level is not None:
                heading_stack = [(lv, title) for lv, title in heading_stack if lv < level]
                heading_stack.append((level, text))
                continue
            heading_path = " > ".join(title for _, title in heading_stack)
            blocks.append(TextBlock(text=text, heading_path=heading_path))
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            text = normalize_text(_table_to_text(table))
            if text:
                heading_path = " > ".join(title for _, title in heading_stack)
                blocks.append(TextBlock(text=text, heading_path=heading_path))

    if not blocks:
        raise ParseError("未从 DOCX 中提取到文本内容")
    return blocks
