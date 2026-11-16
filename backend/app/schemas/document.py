import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collection_id: uuid.UUID
    filename: str
    format: str
    checksum: str
    version: int
    status: str
    failure_reason: str | None
    source_type: str
    source_url: str | None
    fetched_at: datetime | None
    is_enabled: bool
    is_current: bool
    created_at: datetime


class DocumentUpdate(BaseModel):
    is_enabled: bool


class TextDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200_000)

    @field_validator("title", "content")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("标题和内容不能为空")
        return cleaned


class ChunkSnippet(BaseModel):
    chunk_id: uuid.UUID
    ordinal: int
    source_location: str
    text: str


class ChunkContextOut(BaseModel):
    document_id: uuid.UUID
    document_name: str
    format: str
    chunk: ChunkSnippet
    previous: ChunkSnippet | None = None
    next: ChunkSnippet | None = None


class UrlDocumentCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def _strip_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("网址不能为空")
        return cleaned
