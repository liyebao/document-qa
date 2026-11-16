from collections.abc import Callable

from app.services.parsers.base import ParseError, TextBlock, normalize_text
from app.services.parsers.docx import parse_docx
from app.services.parsers.markdown import parse_markdown
from app.services.parsers.pdf import parse_pdf
from app.services.parsers.pptx import parse_pptx
from app.services.parsers.txt import parse_txt
from app.services.parsers.xlsx import parse_xlsx

__all__ = ["ParseError", "TextBlock", "normalize_text", "parse_document"]

# 新增格式只需在此注册解析函数，并同步 storage 的扩展名与内容校验。
_PARSERS: dict[str, Callable[[bytes], list[TextBlock]]] = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "md": parse_markdown,
    "txt": parse_txt,
    "pptx": parse_pptx,
    "xlsx": parse_xlsx,
}


def parse_document(file_format: str, data: bytes) -> list[TextBlock]:
    parser = _PARSERS.get(file_format)
    if parser is None:
        raise ParseError("不支持的文件格式")
    return parser(data)
