from io import BytesIO

from pypdf import PdfReader

from app.services.parsers.base import ParseError, TextBlock, normalize_text


def parse_pdf(data: bytes) -> list[TextBlock]:
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ParseError("PDF 文件损坏或格式不正确") from exc

    blocks: list[TextBlock] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001  单页提取失败不阻断其余页面
            continue
        text = normalize_text(text)
        if text:
            blocks.append(TextBlock(text=text, page=page_number, heading_path=""))

    if not blocks:
        raise ParseError("未从 PDF 中提取到文本，可能是扫描件或空文件")
    return blocks
