import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from app.services.parsers.base import ParseError, TextBlock, normalize_text
from app.services.parsers.headings import heading_for as _heading_for
from app.services.parsers.headings import heading_path as _heading_path
from app.services.parsers.headings import push_heading

_PAGE_NUMBER = re.compile(r"^[-—–\s]*\d{1,4}[-—–\s]*$")
_PAGE_NUMBER_CN = re.compile(r"^第\s*\d+\s*页(?:\s*[/／]\s*共\s*\d+\s*页)?$")


def _blocks_from_page(
    text: str, page_number: int, stack: list[tuple[int, str]]
) -> list[TextBlock]:
    """把一页文本按标题边界切成多个块，标题路径写在块上。

    ``stack`` 跨页复用：章节标题只在出现的那一页写入，后续页的正文
    仍然继承该标题路径。
    """
    lines = text.split("\n")
    non_empty = [index for index, line in enumerate(lines) if line.strip()]
    edge_lines = set(non_empty[:2] + non_empty[-2:])
    blocks: list[TextBlock] = []
    buffer: list[str] = []

    def flush() -> None:
        content = normalize_text("\n".join(buffer))
        if content:
            blocks.append(
                TextBlock(
                    text=content, page=page_number, heading_path=_heading_path(stack)
                )
            )
        buffer.clear()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        # 页眉页脚纯页码：只过滤页面首尾两行，避免误删正文表格里的数字。
        if index in edge_lines and (
            _PAGE_NUMBER.match(stripped) or _PAGE_NUMBER_CN.match(stripped)
        ):
            continue
        heading = _heading_for(stripped, stack)
        if heading is not None:
            flush()
            push_heading(stack, *heading)
            continue
        buffer.append(stripped)

    flush()
    return blocks


def parse_pdf(data: bytes | Path) -> list[TextBlock]:
    try:
        reader = PdfReader(BytesIO(data) if isinstance(data, bytes) else data)
    except Exception as exc:  # noqa: BLE001
        raise ParseError("PDF 文件损坏或格式不正确") from exc

    blocks: list[TextBlock] = []
    heading_stack: list[tuple[int, str]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001  单页提取失败不阻断其余页面
            continue
        text = normalize_text(text)
        if not text:
            continue
        blocks.extend(_blocks_from_page(text, page_number, heading_stack))

    if not blocks:
        raise ParseError("未从 PDF 中提取到文本，可能是扫描件或空文件")
    return blocks
