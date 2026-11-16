import hashlib
import io
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services import storage


def test_save_stream_writes_file_and_returns_checksum(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"
    data = b"%PDF-1.4" + b"x" * 100

    total, checksum = storage.save_stream(target, io.BytesIO(data), limit=1024)

    assert total == len(data)
    assert checksum == hashlib.sha256(data).hexdigest()
    assert target.read_bytes() == data


def test_save_stream_rejects_oversized_and_removes_partial_file(tmp_path: Path) -> None:
    target = tmp_path / "out.bin"

    with pytest.raises(AppError) as exc:
        storage.save_stream(target, io.BytesIO(b"x" * 2048), limit=1024)

    assert exc.value.code == "FILE_TOO_LARGE"
    assert not target.exists()


def test_save_stream_keeps_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "empty.bin"

    total, checksum = storage.save_stream(target, io.BytesIO(b""), limit=1024)

    assert total == 0
    assert checksum == hashlib.sha256(b"").hexdigest()
    assert target.exists()


def test_validate_content_file_rejects_fake_pdf(tmp_path: Path) -> None:
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"not a pdf")

    with pytest.raises(AppError) as exc:
        storage.validate_content_file("pdf", path)

    assert exc.value.code == "UNSUPPORTED_FORMAT"


def test_validate_content_file_accepts_utf8_text(tmp_path: Path) -> None:
    path = tmp_path / "note.md"
    path.write_text("中文内容", encoding="utf-8")

    storage.validate_content_file("md", path)


def test_validate_content_file_rejects_undecodable_text(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_bytes(b"\xff\xfe\x00\x91")

    with pytest.raises(AppError) as exc:
        storage.validate_content_file("txt", path)

    assert exc.value.code == "UNSUPPORTED_FORMAT"
