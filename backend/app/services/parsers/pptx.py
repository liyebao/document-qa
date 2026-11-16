from io import BytesIO

from pptx import Presentation

from app.services.parsers.base import ParseError, TextBlock, normalize_text


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


def parse_pptx(data: bytes) -> list[TextBlock]:
    try:
        presentation = Presentation(BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ParseError("PPTX 文件损坏或格式不正确") from exc

    blocks: list[TextBlock] = []
    for page_number, slide in enumerate(presentation.slides, start=1):
        title_shape = slide.shapes.title
        title = ""
        if title_shape is not None and getattr(title_shape, "has_text_frame", False):
            title = normalize_text(title_shape.text)

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

        content = normalize_text("\n".join(lines))
        if content or title:
            blocks.append(
                TextBlock(
                    text=content or title,
                    page=page_number,
                    heading_path=title,
                )
            )

    if not blocks:
        raise ParseError("未从 PPTX 中提取到文本内容")
    return blocks
