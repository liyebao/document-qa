from collections.abc import Callable
from pathlib import Path

from app.services.parsers.base import ParseError, TextBlock, normalize_text
from app.services.parsers.csv import parse_csv
from app.services.parsers.doc import parse_doc
from app.services.parsers.docx import parse_docx
from app.services.parsers.epub import parse_epub
from app.services.parsers.html import parse_html
from app.services.parsers.image import parse_image
from app.services.parsers.markdown import parse_markdown
from app.services.parsers.pdf import parse_pdf
from app.services.parsers.ppt import parse_ppt
from app.services.parsers.pptx import parse_pptx
from app.services.parsers.txt import parse_txt
from app.services.parsers.xls import parse_xls
from app.services.parsers.xlsx import parse_xlsx

__all__ = ["ParseError", "TextBlock", "normalize_text", "parse_document"]

# 新增格式只需在此注册解析函数，并同步 storage 的扩展名与内容校验。
_PARSERS: dict[str, Callable[[bytes | Path], list[TextBlock]]] = {
    "pdf": parse_pdf,
    "docx": parse_docx,
    "doc": parse_doc,
    "md": parse_markdown,
    "markdown": parse_markdown,
    "txt": parse_txt,
    "pptx": parse_pptx,
    "ppt": parse_ppt,
    "xlsx": parse_xlsx,
    "xls": parse_xls,
    "csv": parse_csv,
    "html": parse_html,
    "htm": parse_html,
    "epub": parse_epub,
    "png": parse_image,
    "jpg": parse_image,
    "jpeg": parse_image,
    "webp": parse_image,
    "gif": parse_image,
    "tiff": parse_image,
    "bmp": parse_image,
}


def parse_document(file_format: str, data: bytes | Path) -> list[TextBlock]:
    parser = _PARSERS.get(file_format)
    if parser is None:
        raise ParseError("不支持的文件格式")
    return parser(data)
