import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import require_collection, require_document, upload_rate_limit
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.collection import Collection
from app.models.document import Document
from app.schemas.document import (
    ChunkContextOut,
    DocumentOut,
    DocumentPreviewOut,
    DocumentUpdate,
    TextDocumentCreate,
    UrlDocumentCreate,
)
from app.services import ingestion, jobs, rendering, storage
from app.services.parsers import ParseError

router = APIRouter(prefix="/api", tags=["documents"])


def _schedule_ingestion(
    background_tasks: BackgroundTasks, db: Session, document_id: uuid.UUID
) -> None:
    """inline 模式用进程内任务，worker 模式写入任务表。"""
    settings = get_settings()
    if settings.ingestion_mode == "worker":
        jobs.enqueue(db, document_id, max_attempts=settings.job_max_attempts)
        db.commit()
    else:
        background_tasks.add_task(ingestion.process_document, document_id)

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt": "application/vnd.ms-powerpoint",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/plain; charset=utf-8",
    "md": "text/plain; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "epub": "application/epub+zip",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "tiff": "image/tiff",
    "bmp": "image/bmp",
}

# 上传的 HTML 是不可信内容：以 text/html 同源 inline 返回等于在本站执行任意脚本，
# 因此只能降级为纯文本、以附件方式下载；需要预览时应走前端自己的净化渲染。
_DOWNLOAD_ONLY_FORMATS = {"html"}


@router.post(
    "/collections/{collection_id}/documents",
    response_model=DocumentOut,
    status_code=202,
)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    collection: Collection = Depends(require_collection),
    db: Session = Depends(get_db),
    _: None = Depends(upload_rate_limit),
) -> DocumentOut:
    # 先按声明大小快速拒绝，再分块落盘：内存峰值只与分块大小相关。
    ingestion.ensure_upload_size(file.size)
    document = ingestion.create_document_from_stream(
        db, collection, file.filename, file.file
    )
    _schedule_ingestion(background_tasks, db, document.id)
    return DocumentOut.model_validate(document)


@router.post(
    "/collections/{collection_id}/documents/text",
    response_model=DocumentOut,
    status_code=202,
)
def create_text_document(
    payload: TextDocumentCreate,
    background_tasks: BackgroundTasks,
    collection: Collection = Depends(require_collection),
    db: Session = Depends(get_db),
    _: None = Depends(upload_rate_limit),
) -> DocumentOut:
    document = ingestion.create_text_document(
        db, collection, payload.title, payload.content
    )
    _schedule_ingestion(background_tasks, db, document.id)
    return DocumentOut.model_validate(document)


@router.post(
    "/collections/{collection_id}/documents/url",
    response_model=DocumentOut,
    status_code=202,
)
def create_url_document(
    payload: UrlDocumentCreate,
    background_tasks: BackgroundTasks,
    collection: Collection = Depends(require_collection),
    db: Session = Depends(get_db),
    _: None = Depends(upload_rate_limit),
) -> DocumentOut:
    document = ingestion.create_url_document(db, collection, payload.url)
    _schedule_ingestion(background_tasks, db, document.id)
    return DocumentOut.model_validate(document)


@router.get("/collections/{collection_id}/documents", response_model=list[DocumentOut])
def list_documents(
    collection: Collection = Depends(require_collection), db: Session = Depends(get_db)
) -> list[DocumentOut]:
    return [
        DocumentOut.model_validate(item) for item in ingestion.list_documents(db, collection)
    ]


@router.post("/documents/{document_id}/replace", response_model=DocumentOut, status_code=202)
def replace_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document: Document = Depends(require_document),
    db: Session = Depends(get_db),
    _: None = Depends(upload_rate_limit),
) -> DocumentOut:
    ingestion.ensure_upload_size(file.size)
    new_document = ingestion.replace_document_from_stream(
        db, document, file.filename, file.file
    )
    _schedule_ingestion(background_tasks, db, new_document.id)
    return DocumentOut.model_validate(new_document)


@router.post("/documents/{document_id}/retry", response_model=DocumentOut, status_code=202)
def retry_document(
    background_tasks: BackgroundTasks,
    document: Document = Depends(require_document),
    db: Session = Depends(get_db),
    _: None = Depends(upload_rate_limit),
) -> DocumentOut:
    retried = ingestion.retry_document(db, document)
    _schedule_ingestion(background_tasks, db, retried.id)
    return DocumentOut.model_validate(retried)


@router.get("/documents/{document_id}/file")
def get_document_file(document: Document = Depends(require_document)) -> FileResponse:
    """返回原文件；PDF 可直接在浏览器中打开并跳到指定页。"""
    path = storage.stored_path(document.storage_path)
    if not path.is_file():
        raise AppError("NOT_FOUND", "原文件不存在或已被清理", 404)
    download_only = document.format in _DOWNLOAD_ONLY_FORMATS
    media_type = _MEDIA_TYPES.get(document.format, "application/octet-stream")
    if download_only:
        media_type = "text/plain; charset=utf-8"
    return FileResponse(
        path,
        media_type=media_type,
        filename=document.filename,
        content_disposition_type="attachment" if download_only else "inline",
        headers={"Cache-Control": "private, max-age=60"},
    )


# iframe 内只允许内联样式：禁止脚本、外部资源，避免上传内容在同源下执行。
_PREVIEW_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:;"
)


def _preview_error_page(message: str) -> str:
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\" />"
        "<style>body{margin:0;padding:32px;font-family:system-ui,'Microsoft YaHei',sans-serif;"
        "font-size:14px;color:#71809A;line-height:1.8}</style></head>"
        f"<body>{message}</body></html>"
    )


@router.get("/documents/{document_id}/render", response_class=HTMLResponse)
def render_document_preview(
    document: Document = Depends(require_document),
) -> HTMLResponse:
    """按原文件重新排版成 HTML，供抽屉内预览。

    和 /preview 的区别：那个返回入库后的片段文本，这个从原文件重新生成
    带标题层级、表格、分页的页面，接近"打开原文件"的效果。
    """
    path = storage.stored_path(document.storage_path)
    if not path.is_file():
        return HTMLResponse(
            _preview_error_page("原文件不存在或已被清理"), status_code=404
        )
    if document.format in {"html", "htm"}:
        # 上传的 HTML 本身就是"原文"，交给 sandbox iframe 隔离渲染。
        content = path.read_text(encoding="utf-8", errors="replace")
        return HTMLResponse(content=content, headers={"Content-Security-Policy": _PREVIEW_CSP})
    try:
        content = rendering.render_document(path, document.format)
    except ParseError as exc:
        return HTMLResponse(_preview_error_page(str(exc)), status_code=422)
    return HTMLResponse(content=content, headers={"Content-Security-Policy": _PREVIEW_CSP})


@router.get("/documents/{document_id}/preview", response_model=DocumentPreviewOut)
def get_document_preview(
    document: Document = Depends(require_document), db: Session = Depends(get_db)
) -> DocumentPreviewOut:
    """返回解析后的片段序列，供抽屉内预览与引用定位。"""
    return ingestion.build_document_preview(db, document)


@router.get(
    "/documents/{document_id}/chunks/{chunk_id}/context",
    response_model=ChunkContextOut,
)
def get_chunk_context(
    chunk_id: uuid.UUID,
    document: Document = Depends(require_document),
    db: Session = Depends(get_db),
) -> ChunkContextOut:
    """返回引用片段及前后各一段，供前端展开核对原文。"""
    return ingestion.get_chunk_context(db, document, chunk_id)


@router.patch("/documents/{document_id}", response_model=DocumentOut)
def update_document(
    payload: DocumentUpdate,
    document: Document = Depends(require_document),
    db: Session = Depends(get_db),
) -> DocumentOut:
    updated = ingestion.set_document_enabled(db, document, payload.is_enabled)
    return DocumentOut.model_validate(updated)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document: Document = Depends(require_document), db: Session = Depends(get_db)
) -> Response:
    ingestion.soft_delete_document(db, document)
    return Response(status_code=204)
