import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
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


def _message_out(message: Message, citations: list[Citation]) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        status=message.status,
        created_at=message.created_at,
        citations=[CitationOut.model_validate(item) for item in citations],
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
