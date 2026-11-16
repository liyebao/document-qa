import json

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import ask_rate_limit, get_current_user, require_conversation
from app.core.errors import AppError
from app.db.session import get_db
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.conversation import (
    ConversationDetail,
    MessageCreate,
    MessageExchange,
    MessageOut,
)
from app.services import answering, collections, conversations

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation: Conversation = Depends(require_conversation),
    db: Session = Depends(get_db),
) -> ConversationDetail:
    return conversations.conversation_detail(db, conversation)


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
    """SSE 流式回答；事件依次为 status / delta / done 或 error。"""
    collection = collections.get_collection_or_error(db, conversation.collection_id, user)
    user_message, history = conversations.start_question(
        db, conversation, collection, payload.content
    )

    def event_stream():
        try:
            for item in answering.stream_answer(
                db,
                conversation,
                collection,
                user_message.content,
                history,
                payload.document_ids,
            ):
                data = item["data"]
                if item["event"] == "done":
                    data["user_message"] = MessageOut.model_validate(
                        user_message
                    ).model_dump(mode="json")
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
        finally:
            conversations.rename_conversation_from_question(
                db, conversation, user_message
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
