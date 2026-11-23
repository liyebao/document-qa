"""表格类资料的公共转换：二维单元格 → Markdown 表格文本块。

XLSX、XLS、CSV 三种来源共用同一套「首行为表头、按行数分块、空表头补列名」
规则，避免同一种表格因为文件格式不同被切成不同形状。
"""

from app.services.parsers.base import TextBlock, normalize_text

# 单个片段保留的表行数；过多行会被切片逻辑再次截断，导致表头丢失。
MAX_ROWS_PER_BLOCK = 40
MAX_COLUMNS = 40


def _cell_text(value: str) -> str:
    """单元格文本：压掉换行与多余空白，并转义 Markdown 表格的分隔符。

    三种表格来源（xlsx/xls/csv）都在这里统一处理，避免同一个单元格因为
    文件格式不同被渲染成不同的形状。
    """

    return " ".join(str(value).split()).replace("|", "\\|")


def markdown_table(header: list[str], rows: list[list[str]]) -> str:
    head = [_cell_text(cell) for cell in header]
    lines = [
        "| " + " | ".join(head) + " |",
        "| " + " | ".join("---" for _ in head) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_cell_text(cell) for cell in row) + " |" for row in rows
    )
    return "\n".join(lines)


def blocks_from_rows(rows: list[list[str]], *, heading_path: str = "") -> list[TextBlock]:
    """把二维表格转成 Markdown 表格块；第一行视为表头。"""
    cleaned = [row[:MAX_COLUMNS] for row in rows if any(cell for cell in row)]
    if not cleaned:
        return []

    width = max(len(row) for row in cleaned)
    padded = [row + [""] * (width - len(row)) for row in cleaned]
    header = list(padded[0])
    for index, name in enumerate(header):
        if not name:
            header[index] = f"列{index + 1}"

    body = padded[1:]
    if not body:
        return [
            TextBlock(
                text=normalize_text(markdown_table(header, [])),
                heading_path=heading_path,
            )
        ]

    blocks: list[TextBlock] = []
    for start in range(0, len(body), MAX_ROWS_PER_BLOCK):
        part = body[start : start + MAX_ROWS_PER_BLOCK]
        blocks.append(
            TextBlock(
                text=normalize_text(markdown_table(header, part)),
                heading_path=heading_path,
            )
        )
    return blocks
