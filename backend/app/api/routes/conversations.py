import json
import uuid

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import ask_rate_limit, get_current_user, require_conversation
from app.core.errors import AppError
from app.db.session import get_db
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.conversation import (
    ConversationDetail,
    ConversationListItem,
    ConversationOut,
    ConversationTitleUpdate,
    MessageCreate,
    MessageExchange,
    MessageOut,
)
from app.services import answering, collections, conversations

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationListItem])
def list_recent_conversations(
    collection_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConversationListItem]:
    """跨资料集的最近会话（侧边栏用），按最近活动时间倒序。"""
    rows = conversations.list_recent_conversations(
        db, user, limit=limit, offset=offset, collection_id=collection_id, keyword=q
    )
    return [
        ConversationListItem(
            id=conversation.id,
            collection_id=conversation.collection_id,
            title=conversation.title,
            created_at=conversation.created_at,
            collection_name=collection_name,
            updated_at=updated_at,
        )
        for conversation, collection_name, updated_at in rows
    ]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation: Conversation = Depends(require_conversation),
    db: Session = Depends(get_db),
) -> ConversationDetail:
    return conversations.conversation_detail(db, conversation)


@router.patch("/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    payload: ConversationTitleUpdate,
    conversation: Conversation = Depends(require_conversation),
    db: Session = Depends(get_db),
) -> ConversationOut:
    """只改标题；归属校验在 require_conversation 内完成，非本人会话一律 404。"""
    updated = conversations.rename_conversation(db, conversation, payload.title)
    return ConversationOut.model_validate(updated)


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation: Conversation = Depends(require_conversation),
    db: Session = Depends(get_db),
) -> Response:
    conversations.delete_conversation(db, conversation)
    return Response(status_code=204)


@router.post("/{conversation_id}/messages", response_model=MessageExchange)
def create_message(
    payload: MessageCreate,
    conversation: Conversation = Depends(require_conversation),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(ask_rate_limit),
) -> MessageExchange:
    collection = collections.get_collection_or_error(db, conversation.collection_id, user)
    return conversations.ask_question(
        db, conversation, collection, payload.content, payload.document_ids
    )


@router.post("/{conversation_id}/messages/stream")
def create_message_stream(
    payload: MessageCreate,
    conversation: Conversation = Depends(require_conversation),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: None = Depends(ask_rate_limit),
) -> StreamingResponse:
    """SSE 流式回答；事件依次为 status / delta / done 或 error。

    用户提问与标题在这里用请求会话写完即提交，流内只传 id 和已加载的数据，
    避免整个生成过程占着数据库连接。
    """
    collection = collections.get_collection_or_error(db, conversation.collection_id, user)
    user_message, history = conversations.start_question(
        db, conversation, collection, payload.content
    )
    conversations.rename_conversation_from_question(db, conversation, user_message)

    conversation_id = conversation.id
    collection_id = collection.id
    question = user_message.content
    document_ids = payload.document_ids
    user_payload = MessageOut.model_validate(user_message).model_dump(mode="json")

    def event_stream():
        try:
            for item in answering.stream_answer(
                conversation_id,
                collection_id,
                question,
                history,
                document_ids,
            ):
                data = item["data"]
                if item["event"] == "done":
                    data["user_message"] = user_payload
                payload_data = json.dumps(data, ensure_ascii=False)
                yield f"event: {item['event']}\ndata: {payload_data}\n\n"
        except AppError as exc:
            payload_data = json.dumps(
                {"code": exc.code, "message": exc.message}, ensure_ascii=False
            )
            yield f"event: error\ndata: {payload_data}\n\n"
        except Exception:  # noqa: BLE001  连接已建立，只能转成事件通知前端
            payload_data = json.dumps(
                {"code": "INTERNAL_ERROR", "message": "回答失败，请稍后重试"},
                ensure_ascii=False,
            )
            yield f"event: error\ndata: {payload_data}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
