import io
import zipfile

import pytest

from app.core.errors import AppError
from app.services.storage import detect_format, validate_content


def test_detect_format_discards_path_components() -> None:
    assert detect_format("../../etc/report.PDF") == ("report.PDF", "pdf")


def test_detect_format_rejects_unsupported_extension() -> None:
    with pytest.raises(AppError) as exc:
        detect_format("note.exe")
    assert exc.value.code == "UNSUPPORTED_FORMAT"


def test_detect_format_accepts_new_sources() -> None:
    assert detect_format("note.txt") == ("note.txt", "txt")
    assert detect_format("slides.PPTX") == ("slides.PPTX", "pptx")
    assert detect_format("table.xlsx") == ("table.xlsx", "xlsx")


def test_office_formats_require_internal_markers() -> None:
    for file_format, marker in (
        ("pptx", "ppt/presentation.xml"),
        ("xlsx", "xl/workbook.xml"),
    ):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(marker, "<root/>")
        validate_content(file_format, buffer.getvalue())
        with pytest.raises(AppError):
            validate_content(file_format, b"not a zip")


def test_txt_accepts_utf8_and_gbk() -> None:
    validate_content("txt", "中文内容".encode())
    validate_content("txt", "中文内容".encode("gbk"))


def test_pdf_signature_is_required() -> None:
    validate_content("pdf", b"%PDF-1.7\nbody")
    with pytest.raises(AppError):
        validate_content("pdf", b"<html>not a pdf</html>")


def test_docx_must_contain_word_document() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
    validate_content("docx", buffer.getvalue())

    empty_zip = io.BytesIO()
    with zipfile.ZipFile(empty_zip, "w") as archive:
        archive.writestr("hello.txt", "hello")
    with pytest.raises(AppError):
        validate_content("docx", empty_zip.getvalue())
    with pytest.raises(AppError):
        validate_content("docx", b"not a zip")


def test_markdown_accepts_utf8_and_gbk() -> None:
    validate_content("md", "中文内容".encode())
    validate_content("md", "中文内容".encode("gbk"))
    with pytest.raises(AppError):
        validate_content("md", b"\xff\xfe\xff\xfe")
