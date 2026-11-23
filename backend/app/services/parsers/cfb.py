"""OLE2（Compound File Binary）最小读取器。

Word 97（.doc）、PowerPoint 97（.ppt）、Excel 97（.xls）都是「复合文档」：
文件本身是一组分扇区，先由 FAT/miniFAT 串成目录，再从目录里按名字取出流。

项目没有引入 olefile 这类依赖，这里只实现按名字取流所必需的部分：
校验容器签名、列出流名、读取指定流。实现依据为 [MS-CFB] 公开格式说明，
不依赖任何第三方库，也不解析与取文本无关的结构。
"""

from __future__ import annotations

import mmap
import os
import struct
from dataclasses import dataclass
from pathlib import Path

SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_HEADER_BYTES = 512
_DIR_ENTRY_BYTES = 128
_DIFAT_HEADER_ENTRIES = 109
_END_OF_CHAIN = 0xFFFFFFFE
_FREE_SECTOR = 0xFFFFFFFF
_MAX_REGULAR_SECTOR = 0xFFFFFFFA
# 损坏文件可能让 FAT 链成环，遍历步数必须设上限。
_MAX_CHAIN_STEPS = 1 << 22

_ENTRY_TYPE_STORAGE = 1
_ENTRY_TYPE_STREAM = 2
_ENTRY_TYPE_ROOT = 5


class CfbError(Exception):
    """不是有效的 OLE2 复合文档，或结构已损坏。"""


@dataclass(frozen=True)
class CfbEntry:
    name: str
    entry_type: int
    start_sector: int
    size: int


class CompoundFile:
    """按名字读取 OLE2 容器中的流。

    支持 `bytes` 与 `Path` 两种来源：走磁盘时用只读 mmap，避免为了校验
    一个 100 MB 的上传文件把它整个读进内存。
    """

    def __init__(self, source: bytes | Path) -> None:
        self._mm: mmap.mmap | None = None
        self._file = None
        if isinstance(source, bytes):
            self._buffer: bytes | mmap.mmap = source
        else:
            try:
                self._file = os.open(Path(source), os.O_RDONLY | getattr(os, "O_BINARY", 0))
                size = os.fstat(self._file).st_size
                # Windows 上零长度文件不能 mmap，直接按空容器处理。
                self._mm = (
                    mmap.mmap(self._file, 0, access=mmap.ACCESS_READ) if size else None
                )
            except OSError as exc:
                self._release()
                raise CfbError("无法读取文件") from exc
            self._buffer = self._mm if self._mm is not None else b""

        self._size = len(self._buffer)
        self._entries: list[CfbEntry] = []
        # 头部或目录解析失败时也要把 fd/mmap 放掉：否则 Windows 上文件被锁，
        # 失败文档的物理文件删不掉，反复重试还会累积句柄。
        try:
            self._parse_header()
            self._read_directory()
        except BaseException:
            self.close()
            raise

    # ------------------------------------------------------------------ 生命周期
    def __enter__(self) -> CompoundFile:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._mm is not None:
            try:
                self._mm.close()
            except BufferError:
                # 仍有切片视图时 mmap 不能关闭；交给 GC 收尾即可。
                pass
            self._mm = None
        self._release()

    def _release(self) -> None:
        if self._file is not None:
            try:
                os.close(self._file)
            except OSError:
                pass
            self._file = None

    # ------------------------------------------------------------------ 头部与扇区
    def _parse_header(self) -> None:
        if self._size < _HEADER_BYTES:
            raise CfbError("文件不足一个扇区，不是复合文档")
        if self._buffer[:8] != SIGNATURE:
            raise CfbError("缺少 OLE2 文件签名")

        self._sector_size = 1 << struct.unpack_from("<H", self._buffer, 0x1E)[0]
        self._mini_sector_size = 1 << struct.unpack_from("<H", self._buffer, 0x20)[0]
        if self._sector_size < 128 or self._mini_sector_size < 8:
            raise CfbError("扇区大小不合法")

        self._fat_sector_count = struct.unpack_from("<I", self._buffer, 0x2C)[0]
        self._first_dir_sector = struct.unpack_from("<I", self._buffer, 0x30)[0]
        self._mini_cutoff = struct.unpack_from("<I", self._buffer, 0x38)[0]
        self._first_mini_fat = struct.unpack_from("<I", self._buffer, 0x3C)[0]
        self._mini_fat_sector_count = struct.unpack_from("<I", self._buffer, 0x40)[0]
        self._first_difat = struct.unpack_from("<I", self._buffer, 0x44)[0]
        self._difat_sector_count = struct.unpack_from("<I", self._buffer, 0x48)[0]

        self._fat = self._read_fat()
        self._mini_fat = self._read_mini_fat()

    def _sector_offset(self, sector_id: int) -> int:
        offset = (sector_id + 1) * self._sector_size
        if sector_id > _MAX_REGULAR_SECTOR or offset >= self._size:
            raise CfbError("扇区编号越界")
        return offset

    def _sector(self, sector_id: int) -> bytes:
        offset = self._sector_offset(sector_id)
        return self._buffer[offset : offset + self._sector_size]

    def _read_fat(self) -> list[int]:
        fat_sector_ids: list[int] = []
        for index in range(_DIFAT_HEADER_ENTRIES):
            sector_id = struct.unpack_from("<I", self._buffer, 0x4C + index * 4)[0]
            if sector_id == _FREE_SECTOR:
                break
            fat_sector_ids.append(sector_id)

        # DIFAT 扇区是一条链：末尾 4 字节指向下一个 DIFAT 扇区。
        pointer = self._first_difat
        per_sector = self._sector_size // 4 - 1
        # 链长度来自文件头的 numDIFAT，不能直接当循环次数：一个 2 KB 的文件
        # 把头里这个 u32 写成 u32 最大值，就能让解析线程空转几十分钟。
        # 因此与文件实际扇区数取 min，并对环做检测。
        max_difat = min(
            max(self._difat_sector_count, 0),
            self._size // self._sector_size + 1,
            _MAX_CHAIN_STEPS,
        )
        seen_difat: set[int] = set()
        for _ in range(max_difat):
            if pointer in {_FREE_SECTOR, _END_OF_CHAIN} or pointer in seen_difat:
                break
            seen_difat.add(pointer)
            block = self._sector(pointer)
            if len(block) < per_sector * 4 + 4:
                break
            for index in range(per_sector):
                sector_id = struct.unpack_from("<I", block, index * 4)[0]
                if sector_id == _FREE_SECTOR:
                    break
                fat_sector_ids.append(sector_id)
            pointer = struct.unpack_from("<I", block, per_sector * 4)[0]

        fat: list[int] = []
        for sector_id in fat_sector_ids[: max(self._fat_sector_count, 0)] or fat_sector_ids:
            block = self._sector(sector_id)
            fat.extend(struct.unpack_from(f"<{len(block) // 4}I", block, 0))
        if not fat:
            raise CfbError("FAT 为空")
        return fat

    def _read_mini_fat(self) -> list[int]:
        if self._mini_fat_sector_count == 0:
            return []
        data = self._read_chain(self._first_mini_fat, self._fat)
        return list(struct.unpack_from(f"<{len(data) // 4}I", data, 0))

    def _read_chain(self, start_sector: int, fat: list[int]) -> bytes:
        chunks: list[bytes] = []
        sector_id = start_sector
        seen: set[int] = set()
        while sector_id not in {_END_OF_CHAIN, _FREE_SECTOR}:
            if sector_id in seen or len(seen) > _MAX_CHAIN_STEPS:
                raise CfbError("FAT 链存在环")
            seen.add(sector_id)
            chunks.append(self._sector(sector_id))
            if sector_id >= len(fat):
                break
            sector_id = fat[sector_id]
        return b"".join(chunks)

    # ------------------------------------------------------------------ 目录
    def _read_directory(self) -> None:
        data = self._read_chain(self._first_dir_sector, self._fat)
        root_start = 0
        root_size = 0
        for offset in range(0, len(data) - _DIR_ENTRY_BYTES + 1, _DIR_ENTRY_BYTES):
            entry = data[offset : offset + _DIR_ENTRY_BYTES]
            name_length = struct.unpack_from("<H", entry, 0x40)[0]
            entry_type = entry[0x42]
            if entry_type == 0 or name_length < 2:
                continue
            name = entry[: name_length - 2].decode("utf-16-le", errors="replace")
            start_sector = struct.unpack_from("<I", entry, 0x74)[0]
            size_low, size_high = struct.unpack_from("<II", entry, 0x78)
            size = size_low | (size_high << 32)
            if entry_type == _ENTRY_TYPE_ROOT:
                root_start, root_size = start_sector, size
                continue
            if entry_type not in {_ENTRY_TYPE_STORAGE, _ENTRY_TYPE_STREAM}:
                continue
            self._entries.append(
                CfbEntry(
                    name=name,
                    entry_type=entry_type,
                    start_sector=start_sector,
                    size=size,
                )
            )
        self._root_start = root_start
        self._root_size = root_size

    # ------------------------------------------------------------------ 对外接口
    @property
    def stream_names(self) -> list[str]:
        return [entry.name for entry in self._entries if entry.entry_type == _ENTRY_TYPE_STREAM]

    def find_stream(self, name: str) -> CfbEntry | None:
        lowered = name.lower()
        for entry in self._entries:
            if entry.entry_type != _ENTRY_TYPE_STREAM:
                continue
            if entry.name.lower() == lowered:
                return entry
        return None

    def has_stream(self, name: str) -> bool:
        return self.find_stream(name) is not None

    def read_stream(self, name: str) -> bytes:
        entry = self.find_stream(name)
        if entry is None:
            raise CfbError(f"缺少 {name} 流")
        return self._read_entry(entry)

    def _read_entry(self, entry: CfbEntry) -> bytes:
        if entry.size == 0:
            return b""
        if entry.size < self._mini_cutoff:
            data = self._read_mini_stream_chain(entry.start_sector)
        else:
            data = self._read_chain(entry.start_sector, self._fat)
        return data[: entry.size]

    def _read_mini_stream_chain(self, start_sector: int) -> bytes:
        if not self._mini_fat:
            raise CfbError("缺少 miniFAT，无法读取小流")
        if self._root_size == 0:
            raise CfbError("缺少根条目，无法定位 mini 流")
        mini_stream = self._read_chain(self._root_start, self._fat)[: self._root_size]

        chunks: list[bytes] = []
        sector_id = start_sector
        seen: set[int] = set()
        while sector_id not in {_END_OF_CHAIN, _FREE_SECTOR}:
            if sector_id in seen or len(seen) > _MAX_CHAIN_STEPS:
                raise CfbError("miniFAT 链存在环")
            seen.add(sector_id)
            offset = sector_id * self._mini_sector_size
            if offset >= len(mini_stream):
                break
            chunks.append(mini_stream[offset : offset + self._mini_sector_size])
            if sector_id >= len(self._mini_fat):
                break
            sector_id = self._mini_fat[sector_id]
        return b"".join(chunks)
