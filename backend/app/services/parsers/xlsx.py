from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from app.services.parsers.base import ParseError, TextBlock
from app.services.parsers.tables import MAX_COLUMNS, blocks_from_rows


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else f"{value:g}"
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


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
                values = [_cell_text(value) for value in row[:MAX_COLUMNS]]
                if any(values):
                    rows.append(values)
            blocks.extend(blocks_from_rows(rows, heading_path=sheet.title))
    finally:
        workbook.close()

    if not blocks:
        raise ParseError("未从 XLSX 中提取到文本内容")
    return blocks
