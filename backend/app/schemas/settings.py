import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProviderInfo(BaseModel):
    key: str
    label: str
    embedding_models: list[str]
    chat_models: list[str]
    rerank_models: list[str] = []
    requires_api_key: bool = True


ModelRole = Literal["embedding", "chat"]
ProviderRole = Literal["embedding", "chat", "both"]


class ModelProviderConfigCreate(BaseModel):
    provider_key: str = Field(min_length=1, max_length=50)
    api_key: str | None = Field(default=None, max_length=512)
    embedding_model: str | None = Field(default=None, max_length=120)
    chat_model: str | None = Field(default=None, max_length=120)
    rerank_model: str | None = Field(default=None, max_length=120)
    role: ProviderRole | None = None

    @field_validator("provider_key")
    @classmethod
    def _strip_provider(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("服务商标识不能为空")
        return value

    @field_validator("api_key", "embedding_model", "chat_model", "rerank_model")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ModelProviderConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_key: str
    embedding_model: str
    chat_model: str
    rerank_model: str
    status: str
    key_masked: str
    last_tested_at: datetime | None
    updated_at: datetime
    is_embedding_default: bool = False
    is_chat_default: bool = False


class EffectiveModelOut(BaseModel):
    config_id: uuid.UUID
    provider_key: str
    provider_label: str
    model: str


class ModelProviderSettingsOut(BaseModel):
    providers: list[ProviderInfo]
    configs: list[ModelProviderConfigOut]
    preferred_embedding_provider: str | None = None
    preferred_chat_provider: str | None = None
    # 后端实际会使用的模型，包含“最近配置”兜底，前端不再自行推导。
    effective_embedding: EffectiveModelOut | None = None
    effective_chat: EffectiveModelOut | None = None
    effective_rerank: EffectiveModelOut | None = None


class ProviderRoleRequest(BaseModel):
    role: ModelRole


class ConnectionTestResult(BaseModel):
    ok: bool
    embedding_ok: bool
    chat_ok: bool
    message: str


class ConnectionTestRequest(BaseModel):
    role: ModelRole | None = None
