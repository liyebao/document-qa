"""Word 97-2003（.doc）文本提取。

.doc 是 OLE2 复合文档：正文在 ``WordDocument`` 流里，但哪一段字符落在
文件的什么位置，要靠 FIB 指向的片段表（table 流里的 CLX → PlcPcd）才能
确定。这里按 [MS-DOC] 的公开结构读取该表，逐段解码：

* ``fCompressed`` 段是单字节字符（高字节为 0），按 GBK 优先、cp1252 兜底；
* 其余段是 UTF-16LE。

不解析样式表（PAPX/CHPX），因此拿不到“标题 1”这类真实样式；
标题只按编号规则推断，与 PDF 的处理保持一致。Word 6.0/95 的 FIB 与
片段表布局不同，明确拒绝并提示另存为 .docx，不猜测。
"""

import re
import struct
from pathlib import Path

from app.services.parsers.base import ParseError, TextBlock
from app.services.parsers.cfb import CfbError, CompoundFile
from app.services.parsers.headings import paragraphs_to_blocks

_WORD_IDENT = 0xA5EC
# Word 97 起 nFib >= 193；更早版本（Word 6.0/95）的正文结构不同。
_MIN_N_FIB = 193
# FibRgFcLcb97 中 fcClx/lcbClx 是第 34 对字段（下标 33）。
_FC_CLX_INDEX = 33

_FIELD_INSTRUCTION = re.compile(r"\x13[^\x13\x14\x15]*\x14")
_CONTROL = re.compile(r"[\x00-\x08\x0e-\x1f\x15]")
_TRANSLATE = str.maketrans({"\r": "\n", "\x0b": "\n", "\x07": "\n", "\x1e": "-", "\x1f": ""})


def _u16(buffer: bytes, offset: int) -> int:
    return struct.unpack_from("<H", buffer, offset)[0]


def _u32(buffer: bytes, offset: int) -> int:
    return struct.unpack_from("<I", buffer, offset)[0]


def _fc_lcb_block(word: bytes) -> int:
    """返回 FibRgFcLcbBlob 的起始偏移。

    FIB 的变长区依次是 csw/FibRgW97、cslw/FibRgLw97、cbRgFcLcb，
    长度字段本身决定后续偏移，不能写死常量。
    """
    csw = _u16(word, 0x20)
    offset = 0x22 + csw * 2
    cslw = _u16(word, offset)
    offset += 2 + cslw * 4
    return offset + 2


def _plcpcd(clx: bytes) -> bytes:
    """从 CLX 中取出 PlcPcd（Prc 块在前，Pcdt 在其后）。"""
    offset = 0
    while offset < len(clx):
        kind = clx[offset]
        if kind == 0x01:
            length = _u16(clx, offset + 1)
            offset += 3 + length
            continue
        if kind == 0x02:
            length = _u32(clx, offset + 1)
            return clx[offset + 5 : offset + 5 + length]
        break
    raise ParseError("DOC 文件缺少片段表，无法定位正文，建议另存为 .docx")


def _decode_single_byte(raw: bytes) -> str:
    """8 位字符段：严格的 GBK 优先，失败再按 cp1252 解释。"""
    try:
        return raw.decode("gbk")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _raw_text(word: bytes, plc: bytes) -> str:
    """按 PlcPcd 的字符位置与 fc 指针拼接全文。"""
    piece_count = (len(plc) - 4) // 12
    if piece_count <= 0:
        raise ParseError("DOC 文件缺少片段表，无法定位正文，建议另存为 .docx")

    positions = struct.unpack_from(f"<{piece_count + 1}I", plc, 0)
    pieces_offset = 4 * (piece_count + 1)
    parts: list[str] = []
    for index in range(piece_count):
        raw_fc = _u32(plc, pieces_offset + index * 8 + 2)
        compressed = bool(raw_fc & 0x40000000)
        offset = raw_fc & 0x3FFFFFFF
        char_count = positions[index + 1] - positions[index]
        if char_count <= 0:
            continue
        if compressed:
            # 压缩段按“半字节偏移”存的是字符偏移，fc 需要除以 2。
            start = offset // 2
            parts.append(_decode_single_byte(word[start : start + char_count]))
        else:
            start = offset
            parts.append(
                word[start : start + char_count * 2].decode("utf-16-le", errors="replace")
            )
    return "".join(parts)


def _clean(text: str) -> list[str]:
    """清理域代码与 Word 控制字符，返回按页切分的文本。"""
    for _ in range(3):
        # 域代码格式为 \x13 指令 \x14 结果 \x15，只保留结果。
        stripped = _FIELD_INSTRUCTION.sub("", text)
        if stripped == text:
            break
        text = stripped
    text = text.replace("\xa0", " ").translate(_TRANSLATE)
    return text.split("\x0c")


def parse_doc(data: bytes | Path) -> list[TextBlock]:
    source = data if isinstance(data, bytes) else Path(data)
    try:
        with CompoundFile(source) as container:
            if not container.has_stream("WordDocument"):
                raise ParseError("文件缺少 WordDocument 流，不是有效的 Word 文档")
            word = container.read_stream("WordDocument")
            table_name = "1Table" if _u16(word, 0x0A) & 0x0200 else "0Table"
            table = (
                container.read_stream(table_name)
                if container.has_stream(table_name)
                else b""
            )
    except CfbError as exc:
        raise ParseError("DOC 文件损坏或格式不正确") from exc

    if len(word) < 0x22 or _u16(word, 0) != _WORD_IDENT:
        raise ParseError("DOC 文件损坏或格式不正确")
    if _u16(word, 0x02) < _MIN_N_FIB:
        raise ParseError("仅支持 Word 97 及以上版本的 .doc，请另存为 .docx 后重新上传")

    fc_clx, lcb_clx = struct.unpack_from("<II", word, _fc_lcb_block(word) + _FC_CLX_INDEX * 8)
    if lcb_clx == 0 or not table:
        raise ParseError("DOC 文件缺少片段表，无法定位正文，建议另存为 .docx")

    text = _raw_text(word, _plcpcd(table[fc_clx : fc_clx + lcb_clx]))

    blocks: list[TextBlock] = []
    heading_stack: list[tuple[int, str]] = []
    for page_number, page_text in enumerate(_clean(text), start=1):
        paragraphs = _CONTROL.sub("", page_text).split("\n")
        if not any(paragraph.strip() for paragraph in paragraphs):
            continue
        blocks.extend(
            paragraphs_to_blocks(paragraphs, page=page_number, stack=heading_stack)
        )

    if not blocks:
        raise ParseError("未从 DOC 中提取到文本内容（可能是只含图片或表格的文档）")
    return blocks
