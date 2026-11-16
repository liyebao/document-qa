import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile
from fastapi.responses import FileResponse
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
    DocumentUpdate,
    TextDocumentCreate,
    UrlDocumentCreate,
)
from app.services import ingestion, jobs

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
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "md": "text/plain; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}


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
    path = Path(document.storage_path)
    if not path.is_file():
        raise AppError("NOT_FOUND", "原文件不存在或已被清理", 404)
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES.get(document.format, "application/octet-stream"),
        filename=document.filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=60"},
    )


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
