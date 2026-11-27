"""计数/全量类问题的原文补证。

top_k 片段只能证明“看到了某一条”，不能证明“总共只有这些条”。
这类问题按命中文档的完整片段序列补齐正文，再看首尾编号是否有缺口。
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import DOCUMENT_STATUS_READY, Document

# 只补命中过的文档，且限制总量，避免把整座资料库都塞进提示词。
MAX_FULL_SCAN_CHUNKS = 60
MAX_FULL_SCAN_CHARS = 24000

_FULL_SCAN_PATTERN = re.compile(
    r"多少条|几条|条数|总共|共计|总数|一共|全部|所有|有哪些|"
    r"最后一条|第一条|最高.{0,8}条|最低.{0,8}条|共.{0,4}页|多少页"
)


def needs_full_document(question: str) -> bool:
    """问题是否要求全量/计数结论，而不是单条事实。"""
    return bool(_FULL_SCAN_PATTERN.search(question))


def fetch_document_chunks(
    db: Session,
    *,
    collection_id: uuid.UUID,
    document_ids: list[uuid.UUID],
    limit: int = MAX_FULL_SCAN_CHUNKS,
) -> list[tuple[Chunk, Document]]:
    """按文档与片段序号取回命中文档的原文，权限与可用状态在 SQL 中过滤。"""
    if not document_ids:
        return []
    stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .join(Collection, Document.collection_id == Collection.id)
        .where(
            Collection.id == collection_id,
            Document.id.in_(document_ids),
            Document.status == DOCUMENT_STATUS_READY,
            Document.deleted_at.is_(None),
            Document.is_enabled.is_(True),
            Document.is_current.is_(True),
        )
        .order_by(Document.id, Chunk.ordinal.asc())
        .limit(limit)
    )
    return list(db.execute(stmt).all())
