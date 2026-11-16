import re
from dataclasses import dataclass


class ParseError(Exception):
    """文件无法提取有效文本时抛出。"""


@dataclass(frozen=True)
class TextBlock:
    text: str
    page: int | None = None
    heading_path: str = ""


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
