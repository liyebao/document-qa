import re
from dataclasses import dataclass


class ParseError(Exception):
    """文件无法提取有效文本时抛出。"""


@dataclass(frozen=True)
class TextBlock:
    text: str
    page: int | None = None
    heading_path: str = ""
    #: ``"table"`` 表示这块是 Markdown 表格。表格必须按行切，不能按句子切，
    #: 否则一行参数会被劈成两半、表头也会跟着丢。
    kind: str = "text"


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
