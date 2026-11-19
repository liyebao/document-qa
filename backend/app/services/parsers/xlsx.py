from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from app.services.parsers.base import ParseError, TextBlock, normalize_text

# 单个片段保留的表行数；过多行会被切片逻辑再次截断，导致表头丢失。
_MAX_ROWS_PER_BLOCK = 40
_MAX_COLUMNS = 40


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:g}"
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value).replace("\n", " ").replace("|", "\\|").strip()


def _markdown_table(header: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def parse_xlsx(data: bytes | Path) -> list[TextBlock]:
    source = BytesIO(data) if isinstance(data, bytes) else data
    try:
        workbook = load_workbook(source, data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ParseError("XLSX 文件损坏或格式不正确") from exc

    blocks: list[TextBlock] = []
    try:
        for sheet in workbook.worksheets:
            rows: list[list[str]] = []
            for row in sheet.iter_rows(values_only=True):
                values = [_cell_text(value) for value in row[:_MAX_COLUMNS]]
                if any(values):
                    rows.append(values)
            if not rows:
                continue

            width = max(len(row) for row in rows)
            rows = [row + [""] * (width - len(row)) for row in rows]
            header = rows[0]
            for index, name in enumerate(header):
                if not name:
                    header[index] = f"列{index + 1}"

            body = rows[1:]
            if not body:
                blocks.append(
                    TextBlock(
                        text=normalize_text(_markdown_table(header, [])),
                        heading_path=sheet.title,
                    )
                )
                continue

            for start in range(0, len(body), _MAX_ROWS_PER_BLOCK):
                part = body[start : start + _MAX_ROWS_PER_BLOCK]
                blocks.append(
                    TextBlock(
                        text=normalize_text(_markdown_table(header, part)),
                        heading_path=sheet.title,
                    )
                )
    finally:
        workbook.close()

    if not blocks:
        raise ParseError("未从 XLSX 中提取到文本内容")
    return blocks
