import codecs
import hashlib
import io
import logging
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

_UPLOAD_CHUNK_BYTES = 1024 * 1024

_EXTENSION_FORMATS = {
    "pdf": "pdf",
    "docx": "docx",
    "md": "md",
    "markdown": "md",
    "txt": "txt",
    "pptx": "pptx",
    "xlsx": "xlsx",
}

SUPPORTED_FORMATS_LABEL = "PDF、DOCX、Markdown、TXT、PPTX 和 XLSX"

# Office Open XML 都是 zip 容器，用内部固定路径确认类型，避免仅改扩展名。
_ZIP_MARKERS = {
    "docx": "word/document.xml",
    "pptx": "ppt/presentation.xml",
    "xlsx": "xl/workbook.xml",
}
_ZIP_LABELS = {"docx": "DOCX", "pptx": "PPTX", "xlsx": "XLSX"}
_TEXT_FORMATS = {"md", "txt"}


def detect_format(filename: str) -> tuple[str, str]:
    """返回 (安全文件名, 格式标识)；不信任用户提供的路径。"""
    safe_name = Path(filename).name.strip()
    if not safe_name:
        raise AppError(
            "UNSUPPORTED_FORMAT", f"仅支持 {SUPPORTED_FORMATS_LABEL} 文件", 415
        )
    suffix = Path(safe_name).suffix.lower().lstrip(".")
    file_format = _EXTENSION_FORMATS.get(suffix)
    if file_format is None:
        raise AppError(
            "UNSUPPORTED_FORMAT", f"仅支持 {SUPPORTED_FORMATS_LABEL} 文件", 415
        )
    return safe_name[:255], file_format


def validate_content(file_format: str, data: bytes) -> None:
    """校验文件头/结构，避免仅改扩展名的任意二进制进入解析器。"""
    if file_format == "pdf":
        if not data.startswith(b"%PDF-"):
            raise AppError("UNSUPPORTED_FORMAT", "文件内容不是有效的 PDF", 415)
        return
    marker = _ZIP_MARKERS.get(file_format)
    if marker is not None:
        label = _ZIP_LABELS[file_format]
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if marker not in archive.namelist():
                    raise AppError(
                        "UNSUPPORTED_FORMAT", f"文件内容不是有效的 {label}", 415
                    )
        except zipfile.BadZipFile as exc:
            raise AppError(
                "UNSUPPORTED_FORMAT", f"文件内容不是有效的 {label}", 415
            ) from exc
        return
    if file_format in _TEXT_FORMATS:
        for encoding in ("utf-8-sig", "gbk"):
            try:
                data.decode(encoding)
                return
            except UnicodeDecodeError:
                continue
        label = "Markdown" if file_format == "md" else "TXT"
        raise AppError(
            "UNSUPPORTED_FORMAT", f"{label} 文件编码无法识别，请使用 UTF-8", 415
        )


def build_storage_path(collection_id: uuid.UUID, document_id: uuid.UUID, file_format: str) -> Path:
    return get_settings().upload_dir / str(collection_id) / f"{document_id}.{file_format}"


def save_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _text_decodes(encoding: str, path: Path) -> bool:
    """分块解码，避免为了校验编码把整份文本读进内存。"""
    decoder = codecs.getincrementaldecoder(encoding)("strict")
    try:
        with path.open("rb") as handle:
            while True:
                block = handle.read(_UPLOAD_CHUNK_BYTES)
                if not block:
                    break
                decoder.decode(block)
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return False
    return True


def save_stream(path: Path, source: BinaryIO, *, limit: int) -> tuple[int, str]:
    """分块落盘并同时计算大小与 sha256；超过 limit 立即中止并删除半成品。

    返回 (字节数, sha256 十六进制)。调用方拿到校验点后即可做重复检测，
    不必再把整个文件读进内存。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("wb") as target:
            while True:
                block = source.read(_UPLOAD_CHUNK_BYTES)
                if not block:
                    break
                total += len(block)
                if total > limit:
                    raise AppError(
                        "FILE_TOO_LARGE",
                        f"文件大小不能超过 {get_settings().max_upload_mb} MB",
                        413,
                    )
                digest.update(block)
                target.write(block)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return total, digest.hexdigest()


def validate_content_file(file_format: str, path: Path) -> None:
    """按文件路径做内容校验，语义与 validate_content 一致但不占用整块内存。"""
    if file_format == "pdf":
        with path.open("rb") as handle:
            if not handle.read(5).startswith(b"%PDF-"):
                raise AppError("UNSUPPORTED_FORMAT", "文件内容不是有效的 PDF", 415)
        return
    marker = _ZIP_MARKERS.get(file_format)
    if marker is not None:
        label = _ZIP_LABELS[file_format]
        try:
            with zipfile.ZipFile(path) as archive:
                if marker not in archive.namelist():
                    raise AppError(
                        "UNSUPPORTED_FORMAT", f"文件内容不是有效的 {label}", 415
                    )
        except zipfile.BadZipFile as exc:
            raise AppError(
                "UNSUPPORTED_FORMAT", f"文件内容不是有效的 {label}", 415
            ) from exc
        return
    if file_format in _TEXT_FORMATS:
        for encoding in ("utf-8-sig", "gbk"):
            if _text_decodes(encoding, path):
                return
        label = "Markdown" if file_format == "md" else "TXT"
        raise AppError(
            "UNSUPPORTED_FORMAT", f"{label} 文件编码无法识别，请使用 UTF-8", 415
        )


def delete_stored_file(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as exc:
        # 物理文件清理失败不应影响数据库软删除，但需要留下可发现的记录
        logger.warning("上传文件清理失败 path=%s error=%s", path, exc.__class__.__name__)
