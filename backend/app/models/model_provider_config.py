import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CONFIG_STATUS_CONFIGURED = "configured"
CONFIG_STATUS_OK = "ok"
CONFIG_STATUS_ERROR = "error"


class ModelProviderConfig(Base):
    __tablename__ = "model_provider_configs"
    __table_args__ = (UniqueConstraint("user_id", "provider_key", name="uq_provider_user_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider_key: Mapped[str] = mapped_column(String(50))
    api_key_ciphertext: Mapped[str] = mapped_column(Text)
    key_version: Mapped[int] = mapped_column(Integer, default=1)
    embedding_model: Mapped[str] = mapped_column(String(120))
    chat_model: Mapped[str] = mapped_column(String(120))
    # 空字符串表示不启用重排。
    rerank_model: Mapped[str] = mapped_column(
        String(120), default="", server_default=""
    )
    status: Mapped[str] = mapped_column(String(32), default=CONFIG_STATUS_CONFIGURED)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
