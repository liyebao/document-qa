"""证明「仅把扩展名改成受支持格式」仍会被内容校验拦下。"""

from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services.storage import (
    SUPPORTED_FORMATS_LABEL,
    detect_format,
    validate_content,
    validate_content_file,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "renamed"

# 这些文件都是纯文本，只是被改名成受支持的二进制格式。
_RENAMED = [
    ("note.pdf", "pdf", "文件内容不是有效的 PDF"),
    ("note.doc", "doc", "文件内容不是有效的 Word 97-2003（DOC）"),
    ("note.png", "png", "文件内容不是有效的 PNG 图片"),
    ("note.xlsx", "xlsx", "文件内容不是有效的 XLSX"),
    ("note.epub", "epub", "文件内容不是有效的 EPUB"),
]


@pytest.mark.parametrize(("name", "file_format", "message"), _RENAMED)
def test_renamed_file_is_rejected_by_path(
    name: str, file_format: str, message: str
) -> None:
    path = FIXTURES / name
    assert path.is_file()
    # 扩展名本身是“合法”的，否则测的就不是内容校验了。
    assert detect_format(name) == (name, file_format)
    with pytest.raises(AppError) as exc:
        validate_content_file(file_format, path)
    assert exc.value.code == "UNSUPPORTED_FORMAT"
    assert exc.value.status_code == 415
    assert message in exc.value.message


@pytest.mark.parametrize(("name", "file_format", "message"), _RENAMED)
def test_renamed_file_is_rejected_in_memory(
    name: str, file_format: str, message: str
) -> None:
    with pytest.raises(AppError) as exc:
        validate_content(file_format, (FIXTURES / name).read_bytes())
    assert exc.value.status_code == 415
    assert message in exc.value.message


def test_supported_label_lists_new_formats() -> None:
    for token in ("DOC", "PPT", "XLS", "CSV", "HTML", "EPUB", "图片"):
        assert token in SUPPORTED_FORMATS_LABEL
    with pytest.raises(AppError) as exc:
        detect_format("archive.rar")
    assert "EPUB" in exc.value.message
    assert exc.value.status_code == 415
