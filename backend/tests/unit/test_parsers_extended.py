import io
import zipfile

import pytest
from PIL import Image

from app.services.parsers import ParseError, parse_document
from app.services.parsers.html_text import blocks_from_html

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


def _epub_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", _CONTAINER)
        archive.writestr("OEBPS/content.opf", _OPF)
        archive.writestr("OEBPS/chapter1.xhtml", _CHAPTER)
    return buffer.getvalue()


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 4), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_parse_csv_builds_markdown_table() -> None:
    blocks = parse_document("csv", "部门,金额\n研发,100\n市场,200\n".encode())
    assert len(blocks) == 1
    assert blocks[0].text.splitlines()[0] == "| 部门 | 金额 |"
    assert "| 研发 | 100 |" in blocks[0].text
    assert blocks[0].heading_path == ""


def test_parse_csv_accepts_gbk() -> None:
    blocks = parse_document("csv", "部门,金额\n研发,100\n".encode("gbk"))
    assert "研发" in blocks[0].text


def test_parse_html_uses_body_text_only() -> None:
    html = (
        "<html><head><title>季度报告</title>"
        "<script>var secret = '不该入库';</script></head>"
        "<body><h1>季度报告</h1><p>营收增长 12%。</p>"
        "<h2>风险</h2><p>供应链紧张。</p></body></html>"
    )
    blocks = parse_document("html", html.encode())
    text = "\n".join(block.text for block in blocks)
    assert "营收增长" in text
    assert "供应链紧张" in text
    assert "不该入库" not in text


def test_html_fallback_keeps_heading_path() -> None:
    html = "<body><h1>季度报告</h1><p>营收增长 12%。</p><h2>风险</h2><p>供应链紧张。</p></body>"
    blocks = blocks_from_html(html)
    assert blocks[0].heading_path == "季度报告"
    assert blocks[-1].heading_path == "季度报告 > 风险"


def test_parse_image_reports_metadata_without_fabricating_ocr_text() -> None:
    blocks = parse_document("png", _png_bytes())
    assert len(blocks) == 1
    assert "未启用 OCR" in blocks[0].text
    assert "像素尺寸：8 × 4" in blocks[0].text


def test_parse_image_rejects_corrupted_bytes() -> None:
    with pytest.raises(ParseError):
        parse_document("png", b"not an image")


def test_parse_epub_walks_spine_in_order() -> None:
    blocks = parse_document("epub", _epub_bytes())
    text = "\n".join(block.text for block in blocks)
    assert "正文内容来自电子书" in text
    assert all(block.heading_path.startswith("知识库手册") for block in blocks)


def test_binary_office_parsers_reject_plain_text() -> None:
    for file_format in ("doc", "ppt", "xls"):
        with pytest.raises(ParseError):
            parse_document(file_format, b"plain text pretending to be office")


def test_ole_parsers_reject_truncated_header() -> None:
    truncated = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64
    for file_format in ("doc", "ppt", "xls"):
        with pytest.raises(ParseError):
            parse_document(file_format, truncated)
