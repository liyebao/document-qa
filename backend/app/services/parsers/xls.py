"""Excel 97-2003（.xls）文本提取。

.xls 是 OLE2 复合文档，正文是 ``Workbook``（早期版本为 ``Book``）流里的
BIFF8 记录序列。重建表格只需要三类信息：

* ``BOUNDSHEET``：工作表名与各表记录的起始偏移；
* ``SST`` + ``CONTINUE``：共享字符串表，单元格文本的实际存放处；
* 单元格记录（``LABELSST``/``NUMBER``/``RK``/``MULRK``/``LABEL``/``BOOLERR``/
  ``FORMULA``+``STRING``）：行号、列号与取值。

SST 的字符数据允许被 CONTINUE 记录从中间切开，切开处会插入一个选项字节
重新指明后续字符是 8 位还是 16 位，读取器必须跨段处理——这也是不能随便
用“按记录独立解码”的原因。BIFF5 及更早版本的记录布局不同，明确拒绝。
"""

import struct
from pathlib import Path

from app.services.parsers.base import ParseError, TextBlock
from app.services.parsers.cfb import CfbError, CompoundFile
from app.services.parsers.tables import MAX_COLUMNS, blocks_from_rows

_BOF = 0x0809
_EOF = 0x000A
_BOUNDSHEET = 0x0085
_SST = 0x00FC
_CONTINUE = 0x003C
_LABELSST = 0x00FD
_LABEL = 0x0204
_NUMBER = 0x0203
_RK = 0x027E
_MULRK = 0x00BD
_BOOLERR = 0x0205
_FORMULA = 0x0006
_STRING = 0x0207

_BIFF8_VERSION = 0x0600
_MAX_STRINGS = 1 << 20
_MAX_SHEETS = 512
_RK_DIV100 = 0x01
_RK_INTEGER = 0x02


def _iter_records(buffer: bytes, start: int = 0):
    """逐条产出 (记录类型, 负载)；长度字段不可信时按实际剩余字节截断。"""
    position = start
    while position + 4 <= len(buffer):
        record_type, length = struct.unpack_from("<HH", buffer, position)
        body = position + 4
        yield record_type, buffer[body : body + length]
        position = body + length


class _SstReader:
    """跨 CONTINUE 边界的 SST 读取器。"""

    def __init__(self, segments: list[bytes]) -> None:
        self._segments = segments
        self._index = 0
        self._offset = 0

    def _seek_segment(self) -> bool:
        while self._index < len(self._segments) and self._offset >= len(
            self._segments[self._index]
        ):
            self._index += 1
            self._offset = 0
        return self._index < len(self._segments)

    def read(self, size: int) -> bytes:
        chunks = bytearray()
        while size > 0 and self._seek_segment():
            segment = self._segments[self._index]
            take = min(size, len(segment) - self._offset)
            chunks += segment[self._offset : self._offset + take]
            self._offset += take
            size -= take
        return bytes(chunks)

    def read_u8(self) -> int:
        data = self.read(1)
        return data[0] if data else 0

    def read_u16(self) -> int:
        data = self.read(2)
        return struct.unpack("<H", data)[0] if len(data) == 2 else 0

    def read_u32(self) -> int:
        data = self.read(4)
        return struct.unpack("<I", data)[0] if len(data) == 4 else 0

    def read_chars(self, count: int, high_byte: bool) -> str:
        """读取 ``count`` 个字符，处理段尾切换与切换处的选项字节。"""
        parts: list[str] = []
        while count > 0 and self._seek_segment():
            segment = self._segments[self._index]
            width = 2 if high_byte else 1
            room = (len(segment) - self._offset) // width
            if room <= 0:
                self._index += 1
                self._offset = 0
                if not self._seek_segment():
                    break
                high_byte = bool(self.read_u8() & 0x01)
                continue
            take = min(count, room)
            chunk = segment[self._offset : self._offset + take * width]
            if high_byte:
                parts.append(chunk.decode("utf-16-le", errors="replace"))
            else:
                parts.append(_decode_single_byte(chunk))
            self._offset += take * width
            count -= take
            if count > 0:
                self._index += 1
                self._offset = 0
                if not self._seek_segment():
                    break
                high_byte = bool(self.read_u8() & 0x01)
        return "".join(parts)


def _decode_single_byte(raw: bytes) -> str:
    try:
        return raw.decode("gbk")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _read_sst(segments: list[bytes]) -> list[str]:
    reader = _SstReader(segments)
    header = reader.read(8)
    if len(header) < 8:
        return []
    unique = min(struct.unpack_from("<I", header, 4)[0], _MAX_STRINGS)
    strings: list[str] = []
    for _ in range(unique):
        length = reader.read_u16()
        flags = reader.read_u8()
        rich = bool(flags & 0x08)
        extended = bool(flags & 0x04)
        runs = reader.read_u16() if rich else 0
        extended_size = reader.read_u32() if extended else 0
        strings.append(reader.read_chars(length, bool(flags & 0x01)))
        if runs:
            reader.read(runs * 4)
        if extended_size:
            reader.read(extended_size)
    return strings


def _shared_strings(buffer: bytes) -> list[str]:
    segments: list[bytes] | None = None
    for record_type, payload in _iter_records(buffer):
        if segments is None:
            if record_type == _SST:
                segments = [payload]
            continue
        if record_type == _CONTINUE:
            segments.append(payload)
            continue
        break
    return _read_sst(segments) if segments else []


def _size(buffer: bytes) -> int:
    if len(buffer) < 4:
        return 0
    return struct.unpack_from("<H", buffer, 0)[0]


def _assert_biff8(buffer: bytes) -> None:
    for record_type, payload in _iter_records(buffer):
        if record_type != _BOF:
            raise ParseError("文件不是有效的 Excel 工作簿")
        version = _size(payload) if len(payload) >= 2 else 0
        if version != _BIFF8_VERSION:
            raise ParseError(
                "仅支持 Excel 97-2003（BIFF8）格式的 .xls，请另存为 .xlsx 后重新上传"
            )
        return
    raise ParseError("文件不是有效的 Excel 工作簿")


def _boundsheets(buffer: bytes) -> list[tuple[str, int]]:
    sheets: list[tuple[str, int]] = []
    for record_type, payload in _iter_records(buffer):
        if record_type != _BOUNDSHEET or len(payload) < 8:
            continue
        offset = struct.unpack_from("<I", payload, 0)[0]
        length = payload[6]
        flags = payload[7]
        raw = payload[8 : 8 + length]
        name = (
            raw.decode("utf-16-le", errors="replace")
            if flags & 0x01
            else _decode_single_byte(raw)
        )
        sheets.append((name, offset))
        if len(sheets) >= _MAX_SHEETS:
            break
    return sheets


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _rk_value(raw: int) -> float:
    """RK 编码：bit0=除以 100，bit1=30 位整数，否则是 double 的高 32 位。"""
    if raw & _RK_INTEGER:
        # 先按 32 位有符号数还原符号位，再右移去掉 2 位标志。
        number = struct.unpack("<i", struct.pack("<I", raw & 0xFFFFFFFC))[0] >> 2
        result = float(number)
    else:
        result = struct.unpack("<d", struct.pack("<Q", (raw & 0xFFFFFFFC) << 32))[0]
    return result / 100 if raw & _RK_DIV100 else result


def _labelled(buffer: bytes) -> str:
    """LABEL 记录的字符数据（cch@6 + grbit@8 + 字符）。"""
    if len(buffer) < 9:
        return ""
    length = struct.unpack_from("<H", buffer, 6)[0]
    flags = buffer[8]
    raw = buffer[9 : 9 + (length * 2 if flags & 0x01 else length)]
    if flags & 0x01:
        return raw.decode("utf-16-le", errors="replace")
    return _decode_single_byte(raw)


def _string_record(buffer: bytes) -> str:
    """STRING（0x0207）记录的字符数据：cch@0 + grbit@2 + 字符。

    公式返回字符串时先写 FORMULA、再跟一条 STRING。它的布局与 LABEL 不同
    （少了 rw/col/ixfe），按 LABEL 的偏移读会得到乱码。
    """
    if len(buffer) < 3:
        return ""
    length = struct.unpack_from("<H", buffer, 0)[0]
    flags = buffer[2]
    raw = buffer[3 : 3 + (length * 2 if flags & 0x01 else length)]
    if flags & 0x01:
        return raw.decode("utf-16-le", errors="replace")
    return _decode_single_byte(raw)


def _sheet_rows(buffer: bytes, start: int, shared: list[str]) -> list[list[str]]:
    cells: dict[tuple[int, int], str] = {}
    pending: tuple[int, int] | None = None

    for record_type, payload in _iter_records(buffer, start):
        if record_type == _EOF:
            break
        if record_type == _LABELSST and len(payload) >= 10:
            row, column, _xf, index = struct.unpack_from("<HHHI", payload, 0)
            cells[(row, column)] = shared[index] if index < len(shared) else ""
        elif record_type == _NUMBER and len(payload) >= 14:
            row, column = struct.unpack_from("<HH", payload, 0)
            cells[(row, column)] = _number(struct.unpack_from("<d", payload, 6)[0])
        elif record_type == _RK and len(payload) >= 10:
            row, column, _xf, raw = struct.unpack_from("<HHHI", payload, 0)
            cells[(row, column)] = _number(_rk_value(raw))
        elif record_type == _MULRK and len(payload) >= 6:
            row, first_column = struct.unpack_from("<HH", payload, 0)
            count = (len(payload) - 6) // 6
            for index in range(count):
                raw = struct.unpack_from("<I", payload, 4 + index * 6 + 2)[0]
                cells[(row, first_column + index)] = _number(_rk_value(raw))
        elif record_type == _BOOLERR and len(payload) >= 8:
            row, column = struct.unpack_from("<HH", payload, 0)
            value, is_error = payload[6], payload[7]
            cells[(row, column)] = "" if is_error else ("TRUE" if value else "FALSE")
        elif record_type == _LABEL and len(payload) >= 9:
            row, column = struct.unpack_from("<HH", payload, 0)
            cells[(row, column)] = _labelled(payload)
        elif record_type == _STRING:
            # STRING 记录跟在 FORMULA 之后，本身不带行列，布局也与 LABEL 不同。
            if pending is not None:
                cells[pending] = _string_record(payload)
            pending = None
        elif record_type == _FORMULA and len(payload) >= 14:
            row, column = struct.unpack_from("<HH", payload, 0)
            result = payload[6:14]
            if result[6:8] == b"\xff\xff":
                kind = result[0]
                if kind == 0:
                    pending = (row, column)
                elif kind == 1:
                    cells[(row, column)] = "TRUE" if result[2] else "FALSE"
                else:
                    cells[(row, column)] = ""
            else:
                cells[(row, column)] = _number(struct.unpack("<d", result)[0])

    if not cells:
        return []

    max_row = max(row for row, _ in cells)
    max_column = min(max(column for _, column in cells), MAX_COLUMNS - 1)
    rows: list[list[str]] = []
    for row in range(max_row + 1):
        values = [cells.get((row, column), "") for column in range(max_column + 1)]
        if any(values):
            rows.append(values)
    return rows


def parse_xls(data: bytes | Path) -> list[TextBlock]:
    source = data if isinstance(data, bytes) else Path(data)
    try:
        with CompoundFile(source) as container:
            stream_name = next(
                (
                    name
                    for name in ("Workbook", "Book")
                    if container.has_stream(name)
                ),
                None,
            )
            if stream_name is None:
                raise ParseError("文件缺少 Workbook 流，不是有效的 Excel 工作簿")
            stream = container.read_stream(stream_name)
    except CfbError as exc:
        raise ParseError("XLS 文件损坏或格式不正确") from exc

    _assert_biff8(stream)
    shared = _shared_strings(stream)

    blocks: list[TextBlock] = []
    for sheet_name, offset in _boundsheets(stream):
        if offset >= len(stream):
            continue
        rows = _sheet_rows(stream, offset, shared)
        blocks.extend(blocks_from_rows(rows, heading_path=sheet_name))

    if not blocks:
        raise ParseError("未从 XLS 中提取到文本内容")
    return blocks
