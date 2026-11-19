import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.ratelimit import (
    ask_limiter,
    reindex_limiter,
    settings_limiter,
    upload_limiter,
)
from app.db.session import get_db
from app.models.collection import Collection
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.user import User
from app.services.local_user import get_local_user


def get_current_user(db: Session = Depends(get_db)) -> User:
    """本地单用户模式：所有请求都归属于同一个本地用户。"""
    return get_local_user(db)


def ask_rate_limit(user: User = Depends(get_current_user)) -> None:
    ask_limiter.hit(f"ask:{user.id}")


def upload_rate_limit(user: User = Depends(get_current_user)) -> None:
    upload_limiter.hit(f"upload:{user.id}")


def reindex_rate_limit(user: User = Depends(get_current_user)) -> None:
    reindex_limiter.hit(f"reindex:{user.id}")


def settings_rate_limit(user: User = Depends(get_current_user)) -> None:
    """模型配置写接口与连接测试共用独立配额，不占用问答额度。"""
    settings_limiter.hit(f"settings:{user.id}")


def require_collection(
    collection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Collection:
    collection = db.scalar(
        select(Collection).where(
            Collection.id == collection_id, Collection.user_id == user.id
        )
    )
    if collection is None:
        raise AppError("NOT_FOUND", "资料集不存在", 404)
    return collection


def require_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Document:
    document = db.scalar(
        select(Document)
        .join(Collection, Document.collection_id == Collection.id)
        .where(
            Document.id == document_id,
            Document.deleted_at.is_(None),
            Collection.user_id == user.id,
        )
    )
    if document is None:
        raise AppError("NOT_FOUND", "文件不存在", 404)
    return document


def require_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user.id
        )
    )
    if conversation is None:
        raise AppError("NOT_FOUND", "会话不存在", 404)
    return conversation
