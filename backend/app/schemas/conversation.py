import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collection_id: uuid.UUID
    title: str
    created_at: datetime


class ConversationTitleUpdate(BaseModel):
    """改名请求：长度按 strip 之后计算，1..200；空串与超长都交给 422。"""

    # 先挡明显异常的请求体，真正的上限以 strip 后的字符数为准。
    title: str = Field(max_length=2000)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or len(cleaned) > 200:
            raise ValueError("标题长度需为 1..200 个字符")
        return cleaned


class ConversationListItem(ConversationOut):
    """侧边栏「最近会话」列表项：额外带资料集名与最近活动时间。

    时间取 max(messages.created_at) 与 created_at 的较大值，这样刚建好、
    还没提问的会话排在列表底部而不是被丢弃。
    """

    collection_name: str
    updated_at: datetime


class CitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    marker_index: int
    document_name: str
    source_location: str
    quote_snapshot: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    status: str
    created_at: datetime
    citations: list[CitationOut] = []
    retrieval_trace: dict = Field(default_factory=dict)


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    # 显式检索范围；省略表示整个资料集。空列表会被拒绝，避免静默检索为空。
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("问题不能为空")
        return cleaned

    @field_validator("document_ids")
    @classmethod
    def _dedupe_documents(cls, value: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if value is None:
            return None
        deduped: list[uuid.UUID] = []
        for item in value:
            if item not in deduped:
                deduped.append(item)
        if not deduped:
            raise ValueError("检索范围不能为空；不限制范围时请省略 document_ids")
        return deduped


class MessageExchange(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
