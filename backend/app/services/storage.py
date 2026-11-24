import codecs
import hashlib
import io
import logging
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

_UPLOAD_CHUNK_BYTES = 1024 * 1024
_HEAD_BYTES = 16

_EXTENSION_FORMATS = {
    "pdf": "pdf",
    "docx": "docx",
    "doc": "doc",
    "md": "md",
    "markdown": "md",
    "txt": "txt",
    "csv": "csv",
    "html": "html",
    "htm": "html",
    "pptx": "pptx",
    "ppt": "ppt",
    "xlsx": "xlsx",
    "xls": "xls",
    "epub": "epub",
    "png": "png",
    "jpg": "jpg",
    "jpeg": "jpeg",
    "webp": "webp",
    "gif": "gif",
    "tiff": "tiff",
    "bmp": "bmp",
}

SUPPORTED_FORMATS_LABEL = (
    "PDF、DOCX/DOC、PPTX/PPT、XLSX/XLS、CSV、Markdown、TXT、HTML、EPUB 和图片文件"
)

# Office Open XML 都是 zip 容器，用内部固定路径确认类型，避免仅改扩展名。
_ZIP_MARKERS = {
    "docx": "word/document.xml",
    "pptx": "ppt/presentation.xml",
    "xlsx": "xl/workbook.xml",
    "epub": "META-INF/container.xml",
}
_ZIP_LABELS = {"docx": "DOCX", "pptx": "PPTX", "xlsx": "XLSX", "epub": "EPUB"}

# Word/Excel/PowerPoint 97-2003 都是 OLE2 复合文档，签名固定为 8 字节魔数。
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_OLE_LABELS = {"doc": "Word 97-2003（DOC）", "ppt": "PowerPoint 97-2003（PPT）", "xls": "Excel 97-2003（XLS）"}

_IMAGE_LABELS = {
    "png": "PNG",
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "webp": "WebP",
    "gif": "GIF",
    "tiff": "TIFF",
    "bmp": "BMP",
}
_TEXT_FORMATS = {"md", "txt", "csv", "html"}
_TEXT_LABELS = {"md": "Markdown", "txt": "TXT", "csv": "CSV", "html": "HTML"}


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


def _image_matches(file_format: str, head: bytes) -> bool:
    """按真实文件头判定图片类型，扩展名与内容不符即拒绝。"""
    if file_format == "png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if file_format in {"jpg", "jpeg"}:
        return head.startswith(b"\xff\xd8\xff")
    if file_format == "gif":
        return head.startswith((b"GIF87a", b"GIF89a"))
    if file_format == "webp":
        return head.startswith(b"RIFF") and head[8:12] == b"WEBP"
    if file_format == "tiff":
        return head.startswith((b"II*\x00", b"MM\x00*"))
    if file_format == "bmp":
        return head.startswith(b"BM")
    return False


def _validate(
    file_format: str,
    head: bytes,
    open_archive: Callable[[], zipfile.ZipFile],
    decodes_text: Callable[[str], bool],
) -> None:
    """三种来源（内存字节、磁盘文件）共用的内容校验。"""
    if file_format == "pdf":
        if not head.startswith(b"%PDF-"):
            raise AppError("UNSUPPORTED_FORMAT", "文件内容不是有效的 PDF", 415)
        return

    marker = _ZIP_MARKERS.get(file_format)
    if marker is not None:
        label = _ZIP_LABELS[file_format]
        try:
            with open_archive() as archive:
                if marker not in archive.namelist():
                    raise AppError(
                        "UNSUPPORTED_FORMAT", f"文件内容不是有效的 {label}", 415
                    )
        except zipfile.BadZipFile as exc:
            raise AppError(
                "UNSUPPORTED_FORMAT", f"文件内容不是有效的 {label}", 415
            ) from exc
        return

    ole_label = _OLE_LABELS.get(file_format)
    if ole_label is not None:
        if not head.startswith(_OLE_SIGNATURE):
            raise AppError(
                "UNSUPPORTED_FORMAT", f"文件内容不是有效的 {ole_label}", 415
            )
        return

    image_label = _IMAGE_LABELS.get(file_format)
    if image_label is not None:
        if not _image_matches(file_format, head):
            raise AppError(
                "UNSUPPORTED_FORMAT", f"文件内容不是有效的 {image_label} 图片", 415
            )
        return

    if file_format in _TEXT_FORMATS:
        # gb18030 是 gbk 的超集：校验用窄编码会把解析器能读的文件挡在 415 之外。
        for encoding in ("utf-8-sig", "gb18030"):
            if decodes_text(encoding):
                return
        label = _TEXT_LABELS[file_format]
        raise AppError(
            "UNSUPPORTED_FORMAT", f"{label} 文件编码无法识别，请使用 UTF-8 或 GB18030", 415
        )


def validate_content(file_format: str, data: bytes) -> None:
    """校验文件头/结构，避免仅改扩展名的任意二进制进入解析器。"""

    def decodes_text(encoding: str) -> bool:
        try:
            data.decode(encoding)
            return True
        except UnicodeDecodeError:
            return False

    _validate(
        file_format,
        data[:_HEAD_BYTES],
        lambda: zipfile.ZipFile(io.BytesIO(data)),
        decodes_text,
    )


def build_storage_path(collection_id: uuid.UUID, document_id: uuid.UUID, file_format: str) -> Path:
    return get_settings().upload_dir / str(collection_id) / f"{document_id}.{file_format}"


def relative_storage_path(
    collection_id: uuid.UUID, document_id: uuid.UUID, file_format: str
) -> str:
    """数据库里只存相对 upload_dir 的路径。

    绝对路径在容器与宿主机之间不通用：容器里是 /app/storage/uploads，Windows
    本机会把同一个字符串写成 \\app\\storage\\uploads\\. 换运行方式后就再也找不到文件。
    """
    return f"{collection_id}/{document_id}.{file_format}"


def stored_path(value: str) -> Path:
    """把数据库里的 storage_path 还原成当前环境的绝对路径。

    新记录是相对路径（<资料集ID>/<文件名>），直接拼 upload_dir。
    历史记录可能带着别的环境的绝对路径，这类路径 is_file() 必然失败，
    但末尾两段仍然有效，同样重新拼一次，避免旧数据整体失效。
    """
    path = Path(value)
    if path.is_file():
        return path
    return get_settings().upload_dir / path.parent.name / path.name


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


def _read_head(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(_HEAD_BYTES)


def validate_content_file(file_format: str, path: Path) -> None:
    """按文件路径做内容校验，语义与 validate_content 一致但不占用整块内存。"""
    _validate(
        file_format,
        _read_head(path),
        lambda: zipfile.ZipFile(path),
        lambda encoding: _text_decodes(encoding, path),
    )


def delete_stored_file(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as exc:
        # 物理文件清理失败不应影响数据库软删除，但需要留下可发现的记录
        logger.warning("上传文件清理失败 path=%s error=%s", path, exc.__class__.__name__)
