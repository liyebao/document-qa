"""回归测试：畸形文件不能拖慢解析器，边界数据不能静默丢失。

这些用例对应一次专项审查里实测到的缺陷，包括 DIFAT 链无上限、句柄泄漏、
EPUB 解压炸弹、XLS STRING 记录布局、数字标题误判、表格单元格未转义等。
"""

import io
import struct
import time
import zipfile
from pathlib import Path
from uuid import UUID

import pytest

from app.services.model_provider import _OLLAMA_THINKING_HEADROOM, _chat_payload, get_provider_spec
from app.services.parsers import ParseError, parse_document
from app.services.parsers.cfb import CompoundFile
from app.services.parsers.headings import heading_for
from app.services.parsers.html_text import blocks_from_html
from app.services.parsers.tables import markdown_table
from app.services.parsers.xls import _string_record
from app.services.query_planner import extract_document_ids
from app.services.storage import validate_content

_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>知识库手册</dc:title>
  </metadata>
  <manifest>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="c1"/>
  </spine>
</package>
"""

_CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>第一章</title></head>
  <body><h1>第一章</h1><p>正文内容来自电子书。</p></body>
</html>
"""

DOC_A = UUID("00000000-0000-0000-0000-0000000000a1")


def _ole_header_with_difat_bomb() -> bytes:
    header = bytearray(512)
    header[0:8] = _OLE_SIGNATURE
    struct.pack_into("<H", header, 0x1E, 9)  # 512 字节扇区
    struct.pack_into("<H", header, 0x20, 6)  # 64 字节 mini 扇区
    struct.pack_into("<I", header, 0x2C, 0)  # FAT 扇区数
    struct.pack_into("<I", header, 0x30, 0xFFFFFFFF)  # 目录起始扇区：空闲
    struct.pack_into("<I", header, 0x38, 4096)  # mini 流阈值
    struct.pack_into("<I", header, 0x3C, 0xFFFFFFFE)  # 无 miniFAT
    struct.pack_into("<I", header, 0x40, 0)
    struct.pack_into("<I", header, 0x44, 0)  # 第一个 DIFAT 扇区 → 扇区 0
    struct.pack_into("<I", header, 0x48, 0xFFFFFFFF)  # DIFAT 扇区数：炸弹
    for index in range(109):
        struct.pack_into("<I", header, 0x4C + index * 4, 0xFFFFFFFF)
    return bytes(header)


def _epub(opf: str = _OPF, chapter: bytes = _CHAPTER.encode(), chapter_name: str = "OEBPS/chapter1.xhtml") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", _CONTAINER)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr(chapter_name, chapter)
    return buffer.getvalue()


# --------------------------------------------------------------------- CFB 加固
def test_difat_chain_length_is_bounded() -> None:
    # 扇区 0 末尾 4 字节为 0 → DIFAT 自环；头里的计数是 u32 最大值。
    # 修复前会按 4.29e9 次循环空转（实测约 74 分钟），修复后应立刻结束。
    data = _ole_header_with_difat_bomb() + b"\x00" * 512
    started = time.monotonic()
    with CompoundFile(data) as cfb:
        assert cfb.stream_names == []
    assert time.monotonic() - started < 2.0


def test_failed_compound_file_releases_file_handle(tmp_path: Path) -> None:
    broken = tmp_path / "broken.doc"
    # 有 OLE 签名、扇区大小字段非法：头部解析阶段就会失败。
    broken.write_bytes(_OLE_SIGNATURE + b"\x00" * 600)
    with pytest.raises(ParseError):
        parse_document("doc", broken)
    # Windows 上句柄没放掉时这里会抛 PermissionError，正是要防的泄漏。
    broken.unlink()
    assert not broken.exists()


# -------------------------------------------------------------------- EPUB 加固
def test_epub_rejects_compression_bomb() -> None:
    bomb = b"<html><body>" + b"\x00" * (8 * 1024 * 1024) + b"</body></html>"
    with pytest.raises(ParseError) as exc:
        parse_document("epub", _epub(chapter=bomb))
    assert "压缩" in str(exc.value) or "过大" in str(exc.value)


def test_epub_decodes_percent_encoded_href() -> None:
    opf = _OPF.replace('href="chapter1.xhtml"', 'href="chapter%201.xhtml#sec"')
    blocks = parse_document(
        "epub",
        _epub(opf=opf, chapter_name="OEBPS/chapter 1.xhtml"),
    )
    assert any("正文内容来自电子书" in block.text for block in blocks)


# --------------------------------------------------------------------- XLS 记录
def test_xls_string_record_uses_its_own_layout() -> None:
    # STRING 记录紧跟 FORMULA：cch@0、grbit@2、字符@3（LABEL 才是 6/8/9）。
    payload = struct.pack("<HB", 10, 0x01) + "HelloWorld".encode("utf-16-le")
    assert _string_record(payload) == "HelloWorld"


# ------------------------------------------------------------------ 数字标题判定
@pytest.mark.parametrize("line", ["3.14 是圆周率", "2024 年营收增长 12%", "2024.10.01 发布"])
def test_body_numbers_are_not_treated_as_headings(line: str) -> None:
    assert heading_for(line, []) is None


@pytest.mark.parametrize(
    ("line", "level"), [("1 安装依赖", 1), ("2.1 系统架构", 2), ("3.2.1 数据库设计", 3)]
)
def test_numbered_headings_are_still_recognised(line: str, level: int) -> None:
    result = heading_for(line, [])
    assert result is not None
    assert result[0] == level


# --------------------------------------------------------------------- 表格转义
def test_markdown_table_escapes_pipes_and_newlines() -> None:
    lines = markdown_table(["a|b\nc"], [["x|y", "z\nw"]]).splitlines()
    assert lines[0] == "| a\\|b c |"
    assert lines[2] == "| x\\|y | z w |"


def test_html_fallback_keeps_table_rows_together() -> None:
    html = "<table><tr><td>营收</td><td>12%</td></tr><tr><td>成本</td><td>8%</td></tr></table>"
    assert [block.text for block in blocks_from_html(html)] == ["营收 | 12%", "成本 | 8%"]


# ------------------------------------------------------------------ 文件名误判
@pytest.mark.parametrize("question", ["如何导入.csv文件", "这个.epub打不开", "文件.doc格式打不开"])
def test_generic_extension_mention_keeps_full_scope(question: str) -> None:
    # 返回 [] 会被上层当成「用户点名了不存在的文件」，直接把检索清空。
    assert extract_document_ids(question, [(DOC_A, "季度报告.pdf")]) is None


def test_missing_explicit_filename_still_narrows_scope() -> None:
    assert extract_document_ids("季度报告.pdf 里说了什么？", [(DOC_A, "预算说明.docx")]) == []


# --------------------------------------------------------------------- 编码一致
def test_validate_content_accepts_gb18030_csv() -> None:
    data = "名称,备注\n甲,\U00020000\n".encode("gb18030")
    validate_content("csv", data)  # 不应抛 UNSUPPORTED_FORMAT


# --------------------------------------------------------------- ollama 思考预算
def test_ollama_chat_payload_reserves_thinking_budget() -> None:
    spec = get_provider_spec("ollama")
    payload = _chat_payload(spec, "qwen3:4b", [{"role": "user", "content": "hi"}], 0.0, 200)
    assert payload["max_tokens"] == 200 + _OLLAMA_THINKING_HEADROOM


def test_openai_chat_payload_keeps_requested_budget() -> None:
    spec = get_provider_spec("openai")
    payload = _chat_payload(spec, "gpt-4o-mini", [{"role": "user", "content": "hi"}], 0.0, 200)
    assert payload["max_tokens"] == 200
