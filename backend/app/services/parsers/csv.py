"""CSV 文本提取：按分隔符解析后转成 Markdown 表格块。

CSV 没有工作表概念，也没有标题层级，因此只填表结构、不编造标题路径；
编码与 TXT 一致按 UTF-8（含 BOM）优先、GB18030 兜底，
分隔符用标准库 Sniffer 探测，探测失败时退回逗号。
"""

import csv
import io
from pathlib import Path

from app.services.parsers.base import ParseError, TextBlock
from app.services.parsers.tables import blocks_from_rows

_ENCODINGS = ("utf-8-sig", "gb18030")
_DELIMITERS = ",;\t|"


def _decode(raw: bytes) -> str:
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("CSV 文件编码无法识别，请使用 UTF-8")


def _rows(text: str) -> list[list[str]]:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=_DELIMITERS)
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    return [
        [cell for cell in row]
        for row in reader
    ]


def parse_csv(data: bytes | Path) -> list[TextBlock]:
    raw = data if isinstance(data, bytes) else data.read_bytes()
    text = _decode(raw)
    if not text.strip():
        raise ParseError("未从 CSV 中提取到文本内容")

    blocks = blocks_from_rows(_rows(text))
    if not blocks:
        raise ParseError("未从 CSV 中提取到文本内容")
    return blocks
