import uuid

from sqlalchemy import ForeignKey, Index, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChunkTerm(Base):
    """片段的倒排词表，供 BM25 计算词频与文档频率。"""

    __tablename__ = "chunk_terms"
    __table_args__ = (Index("ix_chunk_terms_term", "term"),)

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    term: Mapped[str] = mapped_column(Text, primary_key=True)
    tf: Mapped[int] = mapped_column(Integer, default=1)
