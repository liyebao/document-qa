import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.text_utils import escape_like
from app.models.citation import Citation
from app.models.collection import Collection
from app.models.conversation import Conversation
from app.models.message import MESSAGE_ROLE_USER, MESSAGE_STATUS_COMPLETED, Message
from app.models.user import User
from app.schemas.conversation import (
    CitationOut,
    ConversationDetail,
    MessageExchange,
    MessageOut,
)
from app.services import answering
from app.services.parsers.base import normalize_text


def conversation_activity_column() -> ColumnElement[datetime]:
    """会话「最近活动时间」：COALESCE(max(messages.created_at), created_at)。

    会话列表与全局搜索共用这一个表达式，避免两处 SQL 各自漂移。相关子查询
    在数据库内一次算完，不引入 ORM relationship，因此结果条数不会放大查询次数。
    """
    last_message_at = (
        select(func.max(Message.created_at))
        .where(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )
    return func.coalesce(last_message_at, Conversation.created_at)


def list_recent_conversations(
    db: Session,
    user: User,
    *,
    limit: int = 30,
    offset: int = 0,
    collection_id: uuid.UUID | None = None,
    keyword: str | None = None,
) -> list[tuple[Conversation, str, datetime]]:
    """跨资料集的「最近会话」：一次 JOIN 取完，供侧边栏使用。

    不使用 ORM relationship 懒加载（模型上没有 relationship），否则 30 条会话
    会退化成 31 次查询。排序列是 COALESCE(max(messages.created_at), created_at)
    这个计算列，因此 offset 分页而不是 keyset。
    """
    updated_at = conversation_activity_column().label("updated_at")
    stmt = (
        select(Conversation, Collection.name, updated_at)
        .join(Collection, Collection.id == Conversation.collection_id)
        .where(Conversation.user_id == user.id)
    )
    if collection_id is not None:
        stmt = stmt.where(Conversation.collection_id == collection_id)
    if keyword:
        escaped = escape_like(keyword)
        stmt = stmt.where(Conversation.title.ilike(f"%{escaped}%", escape="\\"))
    stmt = (
        stmt.order_by(updated_at.desc(), Conversation.id.desc()).limit(limit).offset(offset)
    )
    return [
        (row[0], row[1], row[2]) for row in db.execute(stmt).all()
    ]


def list_conversations(db: Session, collection: Collection) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.collection_id == collection.id)
            .order_by(Conversation.created_at.desc())
        ).all()
    )


def create_conversation(
    db: Session, user: User, collection: Collection, title: str | None
) -> Conversation:
    conversation = Conversation(
        user_id=user.id,
        collection_id=collection.id,
        title=normalize_text(title)[:200] if title else "新会话",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def delete_conversation(db: Session, conversation: Conversation) -> None:
    db.delete(conversation)
    db.commit()


def rename_conversation(db: Session, conversation: Conversation, title: str) -> Conversation:
    """只改标题；消息与引用不受影响（级联关系由数据库外键负责）。"""
    conversation.title = normalize_text(title)
    db.commit()
    db.refresh(conversation)
    return conversation


def _message_out(message: Message, citations: list[Citation]) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        status=message.status,
        created_at=message.created_at,
        citations=[CitationOut.model_validate(item) for item in citations],
        retrieval_trace=message.retrieval_trace or {},
    )


def _citations_by_message(
    db: Session, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Citation]]:
    if not message_ids:
        return {}
    grouped: dict[uuid.UUID, list[Citation]] = {}
    citations = db.scalars(
        select(Citation)
        .where(Citation.message_id.in_(message_ids))
        .order_by(Citation.created_at.asc())
    ).all()
    for citation in citations:
        grouped.setdefault(citation.message_id, []).append(citation)
    return grouped


def conversation_detail(db: Session, conversation: Conversation) -> ConversationDetail:
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
        ).all()
    )
    grouped = _citations_by_message(db, [message.id for message in messages])
    return ConversationDetail(
        id=conversation.id,
        collection_id=conversation.collection_id,
        title=conversation.title,
        created_at=conversation.created_at,
        messages=[
            _message_out(message, grouped.get(message.id, [])) for message in messages
        ],
    )


def start_question(
    db: Session, conversation: Conversation, collection: Collection, question: str
) -> tuple[Message, list[Message]]:
    """保存用户提问并返回最近历史，供一次性回答与流式回答共用。"""
    if conversation.collection_id != collection.id:
        raise AppError("NOT_FOUND", "会话不存在", 404)

    history = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(6)
        ).all()
    )
    history.reverse()

    user_message = Message(
        conversation_id=conversation.id,
        role=MESSAGE_ROLE_USER,
        content=normalize_text(question),
        status=MESSAGE_STATUS_COMPLETED,
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    return user_message, history


def rename_conversation_from_question(
    db: Session, conversation: Conversation, user_message: Message
) -> None:
    if conversation.title == "新会话":
        conversation.title = user_message.content[:30]
        db.commit()


def ask_question(
    db: Session,
    conversation: Conversation,
    collection: Collection,
    question: str,
    document_ids: list[uuid.UUID] | None = None,
) -> MessageExchange:
    user_message, history = start_question(db, conversation, collection, question)

    result = answering.answer_question(
        db,
        conversation,
        collection,
        user_message.content,
        history,
        document_scope=document_ids,
    )

    rename_conversation_from_question(db, conversation, user_message)

    return MessageExchange(
        user_message=_message_out(user_message, []),
        assistant_message=_message_out(result.message, result.citations),
    )
