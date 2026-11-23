"""PowerPoint 97-2003（.ppt）文本提取。

.ppt 的正文存放在 ``PowerPoint Document`` 流的文本原子中：
``TextHeaderAtom`` 说明该文本框的用途（0=标题、2=备注），紧随其后的
``TextCharsAtom``（UTF-16LE）或 ``TextBytesAtom``（ANSI）才是文字本身。

记录流是容器嵌套结构（容器记录的 recVer 低 4 位为 0xF），这里递归遍历
记录，按「标题原子」把内容分组成幻灯片：每遇到一个标题文本框就开一张新页，
其余文本框归入当前页。页序按记录出现顺序近似（与 pptx 的页码语义一致），
不解析版式、母版与动画。
"""

import struct
from pathlib import Path

from app.services.parsers.base import ParseError, TextBlock, normalize_text
from app.services.parsers.cfb import CfbError, CompoundFile

_TEXT_CHARS_ATOM = 0x0FA0
_TEXT_BYTES_ATOM = 0x0FA8
_TEXT_HEADER_ATOM = 0x0FBA
_CONTAINER_VERSION = 0xF
_MAX_DEPTH = 8
_TEXT_TYPE_TITLE = 0
_TEXT_TYPE_NOTES = 2
_MAX_BLOCKS = 5000


def _walk(data: bytes, start: int, end: int, depth: int = 0):
    """按文档顺序展开记录流，产出 (记录类型, 负载)。"""
    position = start
    limit = min(end, len(data))
    while position + 8 <= limit:
        version_instance, record_type, length = struct.unpack_from("<HHI", data, position)
        body = position + 8
        stop = min(body + length, limit)
        if (version_instance & 0x000F) == _CONTAINER_VERSION and depth < _MAX_DEPTH:
            yield from _walk(data, body, stop, depth + 1)
        else:
            yield record_type, data[body:stop]
        # 记录长度不可信时 position 仍前进 8 字节，不会死循环。
        position = body + length


def _decode_text(record_type: int, payload: bytes) -> str:
    if record_type == _TEXT_CHARS_ATOM:
        return payload.decode("utf-16-le", errors="replace")
    try:
        return payload.decode("gbk")
    except UnicodeDecodeError:
        return payload.decode("cp1252", errors="replace")


def _paragraphs(text: str) -> list[str]:
    cleaned = text.replace("\r", "\n").replace("\x0b", "\n").replace("\x0c", "\n")
    return [line for line in (normalize_text(item) for item in cleaned.split("\n")) if line]


def parse_ppt(data: bytes | Path) -> list[TextBlock]:
    source = data if isinstance(data, bytes) else Path(data)
    try:
        with CompoundFile(source) as container:
            if not container.has_stream("PowerPoint Document"):
                raise ParseError("文件缺少 PowerPoint Document 流，不是有效的 PPT")
            stream = container.read_stream("PowerPoint Document")
    except CfbError as exc:
        raise ParseError("PPT 文件损坏或格式不正确") from exc

    slides: list[tuple[str, list[str]]] = []
    title = ""
    lines: list[str] = []
    pending_type: int | None = None

    for record_type, payload in _walk(stream, 0, len(stream)):
        if record_type == _TEXT_HEADER_ATOM:
            pending_type = struct.unpack_from("<I", payload, 0)[0] if len(payload) >= 4 else None
            continue
        if record_type not in {_TEXT_CHARS_ATOM, _TEXT_BYTES_ATOM}:
            continue
        paragraphs = _paragraphs(_decode_text(record_type, payload))
        if pending_type == _TEXT_TYPE_TITLE:
            # 标题文本框开启新的一页；上一个标题及其正文先落盘。
            if title or lines:
                slides.append((title, lines))
            title = paragraphs[0] if paragraphs else ""
            lines = paragraphs[1:]
        elif pending_type == _TEXT_TYPE_NOTES:
            lines.extend(f"备注：{item}" for item in paragraphs)
        else:
            lines.extend(paragraphs)
        pending_type = None
        if len(slides) >= _MAX_BLOCKS:
            break

    if title or lines:
        slides.append((title, lines))

    blocks: list[TextBlock] = []
    for page_number, (slide_title, slide_lines) in enumerate(slides, start=1):
        content = normalize_text("\n".join(slide_lines))
        if not content and not slide_title:
            continue
        blocks.append(
            TextBlock(
                text=content or slide_title,
                page=page_number,
                heading_path=slide_title,
            )
        )

    if not blocks:
        raise ParseError("未从 PPT 中提取到文本内容（可能是只含图片的幻灯片）")
    return blocks
