import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.ingestion import _validate_upload, ensure_upload_size


def test_ensure_upload_size_rejects_oversized_upload() -> None:
    limit = get_settings().max_upload_mb * 1024 * 1024

    with pytest.raises(AppError) as exc:
        ensure_upload_size(limit + 1)

    assert exc.value.code == "FILE_TOO_LARGE"
    ensure_upload_size(None)


def test_validate_upload_checks_extension_and_content() -> None:
    with pytest.raises(AppError) as exc:
        _validate_upload("note.exe", b"plain text")
    assert exc.value.code == "UNSUPPORTED_FORMAT"

    with pytest.raises(AppError) as exc:
        _validate_upload("fake.pdf", b"not a pdf")
    assert exc.value.code == "UNSUPPORTED_FORMAT"

    with pytest.raises(AppError) as exc:
        _validate_upload("fake.docx", b"not a zip")
    assert exc.value.code == "UNSUPPORTED_FORMAT"

    with pytest.raises(AppError) as exc:
        _validate_upload("fake.md", b"\xff\xff")
    assert exc.value.code == "UNSUPPORTED_FORMAT"


def test_validate_upload_strips_directories_and_keeps_supported_types() -> None:
    name, file_format = _validate_upload("../../资料/说明.md", "# 标题\n\n正文".encode())
    assert name == "说明.md"
    assert file_format == "md"

    pdf_name, pdf_format = _validate_upload("report.pdf", b"%PDF-1.4\n%test")
    assert pdf_name == "report.pdf"
    assert pdf_format == "pdf"


def test_empty_upload_is_rejected() -> None:
    with pytest.raises(AppError) as exc:
        _validate_upload("empty.md", b"")
    assert exc.value.code == "EMPTY_FILE"
