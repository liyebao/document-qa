import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _CollectionNamePayload(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("资料集名称不能为空")
        return value


class CollectionCreate(_CollectionNamePayload):
    pass


class CollectionUpdate(_CollectionNamePayload):
    pass


class CollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    embedding_provider: str | None
    embedding_model: str | None
    embedding_dimension: int | None
    index_version: int
    created_at: datetime


class CollectionSummary(CollectionOut):
    document_count: int = 0


class CollectionReindexRequest(BaseModel):
    """可选指定服务商；不填时使用用户最近保存的 Embedding 配置。"""

    provider_key: str | None = Field(default=None, max_length=50)


class CollectionReindexOut(CollectionOut):
    chunk_count: int
