import hashlib
import logging
import struct
import uuid
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.text_utils import clean_filename_part
from app.db.session import SessionLocal
from app.models.chunk import Chunk
from app.models.chunk_term import ChunkTerm
from app.models.collection import Collection
from app.models.document import (
    DOCUMENT_SOURCE_TEXT,
    DOCUMENT_SOURCE_UPLOAD,
    DOCUMENT_SOURCE_URL,
    DOCUMENT_STATUS_FAILED,
    DOCUMENT_STATUS_PROCESSING,
    DOCUMENT_STATUS_READY,
    Document,
)
from app.schemas.document import (
    ChunkContextOut,
    ChunkSnippet,
    DocumentPreviewBlock,
    DocumentPreviewOut,
)
from app.services import embeddings, storage
from app.services.chunking import chunk_blocks
from app.services.locations import source_location
from app.services.model_provider import get_user_config, preferred_embedding_config
from app.services.parsers import ParseError, parse_document
from app.services.retrieval.tokenizer import tokenize
from app.services.sources import build_markdown_filename, fetch_page

logger = logging.getLogger(__name__)

# 批量写入大小：chunk 行和倒排词行分开控制，避免单条 SQL/单次 commit 过大。
_CHUNK_INSERT_BATCH = 200
_TERM_INSERT_BATCH = 2000
# 以「页」为单位的格式：一页一个标题、一个知识点，切块时按标题断开。
_SLIDE_FORMATS = frozenset({"pptx", "ppt"})


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def ensure_upload_size(size: int | None) -> None:
    """在读取文件内容前先按声明大小拒绝超大上传。"""
    if size is None:
        return
    limit = get_settings().max_upload_mb * 1024 * 1024
    if size > limit:
        raise AppError(
            "FILE_TOO_LARGE",
            f"文件大小不能超过 {get_settings().max_upload_mb} MB",
            413,
        )


def _validate_upload(filename: str, content: bytes) -> tuple[str, str]:
    settings = get_settings()
    if not content:
        raise AppError("EMPTY_FILE", "文件内容为空", 400)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", f"文件大小不能超过 {settings.max_upload_mb} MB", 413)
    safe_name, file_format = storage.detect_format(filename)
    storage.validate_content(file_format, content)
    return safe_name, file_format


def _find_duplicate(db: Session, collection_id, checksum: str) -> Document | None:
    return db.scalar(
        select(Document).where(
            Document.collection_id == collection_id,
            Document.checksum == checksum,
            Document.deleted_at.is_(None),
        )
    )


def _new_document(
    collection: Collection,
    safe_name: str,
    file_format: str,
    checksum: str,
    *,
    version: int = 1,
    supersedes_id: uuid.UUID | None = None,
    source_type: str = DOCUMENT_SOURCE_UPLOAD,
    source_url: str | None = None,
    fetched_at: datetime | None = None,
) -> tuple[Document, Path]:
    document_id = uuid.uuid4()
    path = storage.build_storage_path(collection.id, document_id, file_format)
    document = Document(
        id=document_id,
        collection_id=collection.id,
        filename=safe_name,
        format=file_format,
        checksum=checksum,
        version=version,
        status=DOCUMENT_STATUS_PROCESSING,
        storage_path=storage.relative_storage_path(collection.id, document_id, file_format),
        source_type=source_type,
        source_url=source_url,
        fetched_at=fetched_at,
        is_enabled=True,
        is_current=True,
        supersedes_id=supersedes_id,
    )
    return document, path


def create_document(
    db: Session,
    collection: Collection,
    filename: str | None,
    content: bytes,
    *,
    source_type: str = DOCUMENT_SOURCE_UPLOAD,
    source_url: str | None = None,
    fetched_at: datetime | None = None,
) -> Document:
    if not filename:
        raise AppError(
            "UNSUPPORTED_FORMAT",
            f"文件名为空；仅支持 {storage.SUPPORTED_FORMATS_LABEL} 文件",
            415,
        )
    safe_name, file_format = _validate_upload(filename, content)
    checksum = _checksum(content)
    if _find_duplicate(db, collection.id, checksum) is not None:
        raise AppError("DUPLICATE_FILE", "资料集中已存在内容相同的文件", 409)

    document, path = _new_document(
        collection,
        safe_name,
        file_format,
        checksum,
        source_type=source_type,
        source_url=source_url,
        fetched_at=fetched_at,
    )
    try:
        storage.save_bytes(path, content)
    except OSError as exc:
        raise AppError("INTERNAL_ERROR", "文件保存失败，请重试", 500) from exc

    db.add(document)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        storage.delete_stored_file(str(path))
        raise AppError("DUPLICATE_FILE", "资料集中已存在内容相同的文件", 409) from exc
    db.refresh(document)
    return document


def _store_streamed(
    db: Session,
    collection: Collection,
    filename: str | None,
    source: BinaryIO,
    *,
    version: int = 1,
    supersedes_id: uuid.UUID | None = None,
    source_type: str = DOCUMENT_SOURCE_UPLOAD,
    source_url: str | None = None,
    fetched_at: datetime | None = None,
) -> Document:
    """分块接收上传并落盘，全程不把整份文件读进内存。

    先写入临时文件，校验通过后再原子改名到正式路径；任何一步失败都删除半成品，
    不会留下无法被数据库引用的残文件。
    """
    if not filename:
        raise AppError(
            "UNSUPPORTED_FORMAT",
            f"文件名为空；仅支持 {storage.SUPPORTED_FORMATS_LABEL} 文件",
            415,
        )
    safe_name, file_format = storage.detect_format(filename)
    limit = get_settings().max_upload_mb * 1024 * 1024
    staging = storage.build_storage_path(collection.id, uuid.uuid4(), "uploading")
    total, checksum = storage.save_stream(staging, source, limit=limit)
    try:
        if total == 0:
            raise AppError("EMPTY_FILE", "文件内容为空", 400)
        storage.validate_content_file(file_format, staging)
        if _find_duplicate(db, collection.id, checksum) is not None:
            raise AppError("DUPLICATE_FILE", "资料集中已存在内容相同的文件", 409)

        document, path = _new_document(
            collection,
            safe_name,
            file_format,
            checksum,
            version=version,
            supersedes_id=supersedes_id,
            source_type=source_type,
            source_url=source_url,
            fetched_at=fetched_at,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(path)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise

    db.add(document)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        storage.delete_stored_file(str(path))
        raise AppError("DUPLICATE_FILE", "资料集中已存在内容相同的文件", 409) from exc
    db.refresh(document)
    return document


def create_document_from_stream(
    db: Session,
    collection: Collection,
    filename: str | None,
    source: BinaryIO,
) -> Document:
    """上传路由入口：内存峰值只与分块大小相关，与文件大小无关。"""
    return _store_streamed(db, collection, filename, source)


def _clean_title(title: str, fallback: str) -> str:
    return clean_filename_part(title, fallback)


def create_text_document(
    db: Session, collection: Collection, title: str, content: str
) -> Document:
    """把粘贴的文本按纯文本资料入库（文件名以 .txt 结尾，便于走 TXT 解析器）。"""
    safe_title = _clean_title(title, "粘贴文本")
    data = content.strip().encode("utf-8")
    return create_document(
        db,
        collection,
        f"{safe_title}.txt",
        data,
        source_type=DOCUMENT_SOURCE_TEXT,
    )


def create_url_document(db: Session, collection: Collection, url: str) -> Document:
    """抓取网页正文并作为一份 Markdown 资料入库。"""
    page = fetch_page(url)
    data = page.content.encode("utf-8")
    return create_document(
        db,
        collection,
        build_markdown_filename(page.title),
        data,
        source_type=DOCUMENT_SOURCE_URL,
        source_url=page.final_url,
        fetched_at=datetime.now(UTC),
    )


def replace_document_from_stream(
    db: Session, document: Document, filename: str | None, source: BinaryIO
) -> Document:
    """替换版本的流式入口；版本号与来源信息沿用原文档。"""
    if not document.is_current:
        raise AppError("DOCUMENT_NOT_CURRENT", "只能替换当前版本的文件", 409)
    collection = db.get(Collection, document.collection_id)
    if collection is None:
        raise AppError("NOT_FOUND", "资料集不存在", 404)
    return _store_streamed(
        db,
        collection,
        filename,
        source,
        version=document.version + 1,
        supersedes_id=document.id,
        source_type=document.source_type,
        source_url=document.source_url,
        fetched_at=document.fetched_at,
    )


def get_chunk_context(
    db: Session, document: Document, chunk_id: uuid.UUID
) -> ChunkContextOut:
    """返回引用片段及其前后各一段，用于核对原文上下文。"""
    chunk = db.scalar(
        select(Chunk).where(Chunk.id == chunk_id, Chunk.document_id == document.id)
    )
    if chunk is None:
        raise AppError("NOT_FOUND", "片段不存在", 404)

    previous = db.scalar(
        select(Chunk)
        .where(Chunk.document_id == document.id, Chunk.ordinal < chunk.ordinal)
        .order_by(Chunk.ordinal.desc())
        .limit(1)
    )
    following = db.scalar(
        select(Chunk)
        .where(Chunk.document_id == document.id, Chunk.ordinal > chunk.ordinal)
        .order_by(Chunk.ordinal.asc())
        .limit(1)
    )

    def snippet(item: Chunk) -> ChunkSnippet:
        return ChunkSnippet(
            chunk_id=item.id,
            ordinal=item.ordinal,
            source_location=source_location(item),
            text=item.text,
        )

    return ChunkContextOut(
        document_id=document.id,
        document_name=document.filename,
        format=document.format,
        chunk=snippet(chunk),
        previous=snippet(previous) if previous is not None else None,
        next=snippet(following) if following is not None else None,
    )


# 预览上限：够看清一份长文档的主体，又不至于让浏览器渲染几千个块。
_PREVIEW_MAX_BLOCKS = 400


def build_document_preview(db: Session, document: Document) -> DocumentPreviewOut:
    """按顺序返回解析后的片段，供抽屉内预览与引用高亮。

    只读已经入库的 chunk，不重新解析原文件，因此打开速度与文档大小无关。
    """
    rows = db.scalars(
        select(Chunk)
        .where(Chunk.document_id == document.id)
        .order_by(Chunk.ordinal)
        .limit(_PREVIEW_MAX_BLOCKS + 1)
    ).all()
    truncated = len(rows) > _PREVIEW_MAX_BLOCKS
    blocks = [
        DocumentPreviewBlock(
            chunk_id=item.id,
            ordinal=item.ordinal,
            source_location=source_location(item),
            text=item.text,
        )
        for item in rows[:_PREVIEW_MAX_BLOCKS]
    ]
    return DocumentPreviewOut(
        document_id=document.id,
        document_name=document.filename,
        format=document.format,
        truncated=truncated,
        blocks=blocks,
    )


def list_documents(db: Session, collection: Collection) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(
                Document.collection_id == collection.id,
                Document.deleted_at.is_(None),
                Document.is_current.is_(True),
            )
            .order_by(Document.created_at.desc())
        ).all()
    )


def set_document_enabled(db: Session, document: Document, enabled: bool) -> Document:
    document.is_enabled = enabled
    db.commit()
    db.refresh(document)
    return document


def retry_document(db: Session, document: Document) -> Document:
    """仅允许重试处理失败的文件，避免重复写入已成功的片段。

    用条件更新做 CAS：两个并发“重试”只有一个能把 failed 改成 processing，
    另一个拿到 0 行直接返回 409，不会同时跑两遍入库。
    """
    result = db.execute(
        update(Document)
        .where(
            Document.id == document.id,
            Document.status == DOCUMENT_STATUS_FAILED,
        )
        .values(status=DOCUMENT_STATUS_PROCESSING, failure_reason=None)
    )
    db.commit()
    if not result.rowcount:
        raise AppError("DOCUMENT_NOT_FAILED", "只有处理失败的文件可以重试", 409)
    db.refresh(document)
    return document


def soft_delete_document(db: Session, document: Document) -> None:
    document.deleted_at = datetime.now(UTC)
    document.is_enabled = False
    document.is_current = False
    # 引用快照保留在 citations 中，chunk_id 由外键置空；片段本身可以清理。
    db.execute(delete(Chunk).where(Chunk.document_id == document.id))
    db.commit()
    storage.delete_stored_file(str(storage.stored_path(document.storage_path)))


def mark_stale_documents_failed() -> int:
    """启动时把上次进程中断遗留的 processing 文件标记为可重试失败。

    文件处理在应用进程内执行，进程退出后任务不会恢复；与其让用户看到
    永久“处理中”，不如明确标记失败并允许重试。
    """
    db = SessionLocal()
    try:
        result = db.execute(
            update(Document)
            .where(Document.status == DOCUMENT_STATUS_PROCESSING)
            .values(
                status=DOCUMENT_STATUS_FAILED,
                failure_reason="服务重启导致处理中断，请重新处理该文件",
            )
        )
        db.commit()
        count = result.rowcount or 0
        if count:
            logger.info("已将 %s 个中断的处理任务标记为失败", count)
        return count
    finally:
        db.close()


def _resolve_embedding_config(db: Session, collection: Collection):
    if collection.embedding_provider:
        config = get_user_config(db, collection.user_id, collection.embedding_provider)
        if config is None:
            raise AppError(
                "MODEL_NOT_CONFIGURED",
                "资料集使用的 Embedding 服务配置已被删除，请恢复配置后再处理文件",
                422,
            )
        if not config.embedding_model:
            raise AppError(
                "MODEL_NOT_CONFIGURED",
                "资料集使用的服务商不提供 Embedding 模型，请配置支持 Embedding 的服务商",
                422,
            )
        if collection.embedding_model and config.embedding_model != collection.embedding_model:
            raise AppError(
                "MODEL_PROVIDER_ERROR",
                f"资料集已固定使用 {collection.embedding_model}，"
                "切换模型需要在资料集页面重建索引；请恢复该模型或先重建索引",
                422,
            )
        return config

    config = preferred_embedding_config(db, collection.user_id)
    if config is None:
        raise AppError(
            "MODEL_NOT_CONFIGURED",
            "请先在模型设置中配置支持 Embedding 的服务商（如 OpenAI、百炼或硅基流动）",
            422,
        )
    return config


def _safe_failure(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message[:500]
    if isinstance(exc, ParseError):
        return str(exc)[:500]
    if isinstance(exc, FileNotFoundError):
        return "上传文件不存在，请重新上传"
    # 畸形文件常让解析器漏出结构化异常（截断记录、越界解包、坏 zip）。
    # 统一文案会把这些压成「解析失败」而丢掉了唯一可定位的线索，
    # 因此单独给一条带异常类型的提示。
    if isinstance(
        exc, struct.error | IndexError | KeyError | UnicodeDecodeError | zipfile.BadZipFile
    ):
        return f"文件结构损坏，解析失败（{type(exc).__name__}）"
    return "文件解析或索引失败，请检查文件内容后重试"


def _mark_document_failed(
    db: Session, document_id: uuid.UUID, exc: Exception
) -> None:
    document = db.get(Document, document_id)
    if document is None:
        return
    document.status = DOCUMENT_STATUS_FAILED
    document.failure_reason = _safe_failure(exc)
    try:
        db.commit()
    except Exception:  # noqa: BLE001  失败标记本身不能掩盖原始错误
        db.rollback()


def run_ingestion(document_id: uuid.UUID) -> None:
    """执行入库；失败时标记文档并向上抛出，由调用方决定重试。"""
    db = SessionLocal()
    try:
        _ingest_document(db, document_id)
    except Exception as exc:  # noqa: BLE001  worker 需要知道失败
        db.rollback()
        logger.exception("文档处理失败 document_id=%s", document_id)
        _mark_document_failed(db, document_id, exc)
        raise
    finally:
        db.close()


def process_document(document_id: uuid.UUID) -> None:
    """进程内后台任务入口：失败已落库，不再向上抛出。"""
    try:
        run_ingestion(document_id)
    except Exception:  # noqa: BLE001  失败原因已在 run_ingestion 中记录
        return


def _ingest_document(db: Session, document_id: uuid.UUID) -> None:
    """解析 → 切片 → 向量化 → 入库 → 切换为可检索。"""
    settings = get_settings()
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        return
    collection = db.get(Collection, document.collection_id)
    if collection is None:
        raise AppError("NOT_FOUND", "资料集不存在", 404)

    document.status = DOCUMENT_STATUS_PROCESSING
    document.failure_reason = None
    db.commit()

    path = storage.stored_path(document.storage_path)
    if not path.exists():
        raise FileNotFoundError(document.storage_path)

    blocks = parse_document(document.format, path)
    chunks = chunk_blocks(
        blocks,
        target_tokens=settings.chunk_target_tokens,
        min_tokens=settings.chunk_min_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
        # 幻灯片一页就是一个知识点，按标题切块，不让两页拼进同一块。
        heading_split_tokens=0 if document.format in _SLIDE_FORMATS else None,
        # 片段脱离原文后还要能自证归属：文档名进检索面包屑。
        document_title=document.filename,
    )
    if not chunks:
        raise ParseError("未生成有效文本片段")

    config = _resolve_embedding_config(db, collection)
    vectors = embeddings.embed_texts(config, [chunk.search_text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise AppError("MODEL_PROVIDER_ERROR", "Embedding 返回数量与片段数量不一致", 502)

    dimension = len(vectors[0])
    if dimension == 0:
        raise AppError("MODEL_PROVIDER_ERROR", "Embedding 返回了空向量", 502)
    # 混入不同维度的向量会让后续 vector(N) 检索直接报错，宁可在入库阶段拒绝。
    if any(len(vector) != dimension for vector in vectors):
        raise AppError("MODEL_PROVIDER_ERROR", "Embedding 返回的向量维度不一致", 502)
    if collection.embedding_dimension is None:
        collection.embedding_dimension = dimension
    elif collection.embedding_dimension != dimension:
        raise AppError(
            "MODEL_PROVIDER_ERROR",
            "当前 Embedding 模型维度与资料集已建立的索引不一致，请恢复原模型或到资料集页面重建索引",
            422,
        )
    collection.embedding_provider = config.provider_key
    collection.embedding_model = config.embedding_model

    # 幂等：重试/并发重跑前先清掉该文档已有片段，避免叠加出重复索引。
    db.execute(delete(Chunk).where(Chunk.document_id == document.id))

    # 分批写入：大文档的 chunk_terms 可能几万行，一次性 add 会把整批对象压在
    # 内存里并让事务一直开着；Core executemany + 分批 commit 更稳。
    for start in range(0, len(chunks), _CHUNK_INSERT_BATCH):
        chunk_batch = chunks[start : start + _CHUNK_INSERT_BATCH]
        vector_batch = vectors[start : start + _CHUNK_INSERT_BATCH]
        chunk_rows: list[dict] = []
        term_rows: list[dict] = []
        for chunk, vector in zip(chunk_batch, vector_batch, strict=True):
            terms = Counter(tokenize(chunk.search_text))
            chunk_id = uuid.uuid4()
            chunk_rows.append(
                {
                    "id": chunk_id,
                    "document_id": document.id,
                    "fingerprint": chunk.fingerprint,
                    "ordinal": chunk.ordinal,
                    "text": chunk.text,
                    "heading_path": chunk.heading_path,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "search_text": chunk.search_text,
                    "token_count": sum(terms.values()),
                    "embedding": vector,
                }
            )
            term_rows.extend(
                {"chunk_id": chunk_id, "term": term, "tf": count}
                for term, count in terms.items()
            )
        db.execute(insert(Chunk.__table__), chunk_rows)
        for term_start in range(0, len(term_rows), _TERM_INSERT_BATCH):
            db.execute(
                insert(ChunkTerm.__table__),
                term_rows[term_start : term_start + _TERM_INSERT_BATCH],
            )
        db.commit()

    document.status = DOCUMENT_STATUS_READY
    document.failure_reason = None
    if document.supersedes_id is not None:
        previous = db.get(Document, document.supersedes_id)
        if previous is not None and previous.deleted_at is None:
            previous.is_current = False
            # 旧版本向量不再参与检索，及时删除避免长期占用空间；
            # 历史引用的原文快照保存在 citations 中，不受影响。
            db.execute(delete(Chunk).where(Chunk.document_id == previous.id))
    db.commit()
