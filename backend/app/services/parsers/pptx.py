import re
from collections import Counter
from io import BytesIO
from pathlib import Path

from pptx import Presentation

from app.services.parsers.base import ParseError, TextBlock, normalize_text

_SECTION_LINE = re.compile(r"^\d+(?:\.\d+)+\s*\S.*$")
_BADGE_LINE = re.compile(r"^[①-⑳0-9]{1,3}$")
_PAGE_NUMBER = re.compile(r"^\d{1,3}\s*/\s*\d{1,3}$")
_DECORATION = re.compile(r"^[→·•\-—_|/\\\s]+$")
_HEADING_MAX = 80
_FOOTER_RATIO = 0.4
_FOOTER_MIN_SLIDES = 3


def _shape_lines(shape) -> list[str]:
    """提取一个形状中的段落与表格文本，按出现顺序保留。"""
    lines: list[str] = []
    if getattr(shape, "has_text_frame", False):
        for paragraph in shape.text_frame.paragraphs:
            text = normalize_text(paragraph.text)
            if text:
                lines.append(text)
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            cells = [normalize_text(cell.text) for cell in row.cells]
            if any(cells):
                lines.append(" | ".join(cells))
    return lines


def _slide_lines(slide, title_shape) -> list[str]:
    lines: list[str] = []
    for shape in slide.shapes:
        if title_shape is not None and shape.shape_id == title_shape.shape_id:
            continue
        lines.extend(_shape_lines(shape))

    if slide.has_notes_slide:
        notes_frame = slide.notes_slide.notes_text_frame
        note = normalize_text(notes_frame.text) if notes_frame is not None else ""
        if note:
            lines.append(f"备注：{note}")

    return [line for line in (normalize_text(item) for item in lines) if line]


def _take_section(lines: list[str]) -> tuple[str, list[str]]:
    """把最前面的「5.1 用户管理」这类章节行抽出来当标题前缀。"""
    for index, line in enumerate(lines[:3]):
        if _SECTION_LINE.match(line) and len(line) <= _HEADING_MAX:
            return line, lines[:index] + lines[index + 1 :]
    return "", lines


def _take_title(lines: list[str]) -> str:
    """在去掉章节行、序号徽标后，取第一行做标题。"""
    for line in lines[:4]:
        if _BADGE_LINE.match(line) or _DECORATION.match(line) or _PAGE_NUMBER.match(line):
            continue
        if len(line) > _HEADING_MAX:
            continue
        return line
    return ""


def _footer_lines(slide_bodies: list[list[str]], headings: set[str]) -> set[str]:
    """把在大量幻灯片上原样重复的短行判为页眉页脚。"""
    counter = Counter(line for lines in slide_bodies for line in set(lines))
    if len(slide_bodies) < 2:
        # 单页幻灯片没有「重复」可言，任何一行都可能只是正文。
        return set()
    if len(slide_bodies) < _FOOTER_MIN_SLIDES:
        threshold = len(slide_bodies)
    else:
        threshold = max(_FOOTER_MIN_SLIDES, int(len(slide_bodies) * _FOOTER_RATIO + 0.999))
    return {
        line
        for line, count in counter.items()
        if count >= threshold and len(line) <= _HEADING_MAX and line not in headings
    }


def _clean_body(lines: list[str], footers: set[str]) -> list[str]:
    body: list[str] = []
    for line in lines:
        if line in footers or _PAGE_NUMBER.match(line) or _DECORATION.match(line):
            continue
        body.append(line)
    return body


def parse_pptx(data: bytes | Path) -> list[TextBlock]:
    try:
        presentation = Presentation(BytesIO(data) if isinstance(data, bytes) else data)
    except Exception as exc:  # noqa: BLE001
        raise ParseError("PPTX 文件损坏或格式不正确") from exc

    slides = list(presentation.slides)
    layout: list[tuple[int, str, str, list[str]]] = []
    for page_number, slide in enumerate(slides, start=1):
        title_shape = slide.shapes.title
        placeholder_title = ""
        if title_shape is not None and getattr(title_shape, "has_text_frame", False):
            placeholder_title = normalize_text(title_shape.text)

        raw = _slide_lines(slide, title_shape)
        section, rest = _take_section(raw)
        title = placeholder_title or _take_title(rest)
        parts = [part for part in (section, title) if part]
        heading = " > ".join(dict.fromkeys(parts))
        layout.append((page_number, heading, title, rest))

    headings = {heading for _, heading, _, _ in layout if heading}
    footers = _footer_lines([rest for _, _, _, rest in layout], headings)

    blocks: list[TextBlock] = []
    for page_number, heading, title, rest in layout:
        body = _clean_body(rest, footers)
        content = normalize_text("\n".join(body))
        if not content and title:
            content = title
        if content:
            blocks.append(TextBlock(text=content, page=page_number, heading_path=heading))
        elif heading:
            blocks.append(TextBlock(text=heading, page=page_number, heading_path=heading))

    if not blocks:
        raise ParseError("未从 PPTX 中提取到文本内容")
    return blocks
