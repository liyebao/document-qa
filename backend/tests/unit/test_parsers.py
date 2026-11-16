from io import BytesIO

import pytest
from docx import Document as DocxDocument
from openpyxl import Workbook
from pptx import Presentation

from app.services.parsers import ParseError, parse_document
from app.services.parsers.docx import parse_docx
from app.services.parsers.markdown import parse_markdown
from app.services.parsers.pdf import parse_pdf
from app.services.parsers.pptx import parse_pptx
from app.services.parsers.txt import parse_txt
from app.services.parsers.xlsx import parse_xlsx


def test_markdown_keeps_heading_path_and_sections() -> None:
    blocks = parse_markdown(
        "# 项目\n\n## 风险\n\n进度风险需要提前准备资源。\n\n## 预算\n\n预算尚未确认。".encode()
    )

    assert [block.text for block in blocks] == [
        "进度风险需要提前准备资源。",
        "预算尚未确认。",
    ]
    assert blocks[0].heading_path == "项目 > 风险"
    assert blocks[1].heading_path == "项目 > 预算"


def test_markdown_preserves_fenced_code_and_rejects_empty_content() -> None:
    blocks = parse_markdown(b"```python\nprint('ok')\n```")
    assert "```python" in blocks[0].text

    with pytest.raises(ParseError):
        parse_markdown(b"   \n\n")


def test_docx_extracts_heading_path_and_paragraphs() -> None:
    document = DocxDocument()
    document.add_heading("项目风险", level=1)
    document.add_paragraph("项目存在进度风险。")
    buffer = BytesIO()
    document.save(buffer)

    blocks = parse_docx(buffer.getvalue())

    assert blocks[0].text == "项目存在进度风险。"
    assert blocks[0].heading_path == "项目风险"


def test_invalid_documents_raise_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_pdf(b"not a pdf")
    with pytest.raises(ParseError):
        parse_docx(b"not a zip")
    with pytest.raises(ParseError):
        parse_document("rtf", b"hello")


def test_txt_splits_paragraphs_and_accepts_gbk() -> None:
    blocks = parse_txt("第一段。\n\n第二段。".encode("gbk"))

    assert [block.text for block in blocks] == ["第一段。", "第二段。"]


def test_pptx_keeps_slide_number_and_title() -> None:
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "季度汇报"
    slide.placeholders[1].text = "营收同比增长 20%。"
    buffer = BytesIO()
    presentation.save(buffer)

    blocks = parse_pptx(buffer.getvalue())

    assert blocks[0].page == 1
    assert blocks[0].heading_path == "季度汇报"
    assert "20%" in blocks[0].text


def test_xlsx_converts_sheet_to_markdown_table() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "预算"
    sheet.append(["部门", "金额"])
    sheet.append(["研发", 100])
    buffer = BytesIO()
    workbook.save(buffer)

    blocks = parse_xlsx(buffer.getvalue())

    assert blocks[0].heading_path == "预算"
    assert "部门" in blocks[0].text
    assert "研发" in blocks[0].text
