import re
import uuid

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.text_utils import escape_like
from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import DOCUMENT_STATUS_READY, Document

_INTERROGATIVE_TERMS = {
    "什么",
    "怎么",
    "如何",
    "哪些",
    "哪个",
    "是否",
    "多少",
    "请问",
    "以及",
    "这个",
    "那个",
    "一下",
    "可以",
    "需要",
    "关于",
    "报告",
}
_CJK_RUN = re.compile(r"[\u4e00-\u9fa5]+")
_LATIN_TERM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{1,}")


def extract_terms(query: str, max_terms: int = 16) -> list[str]:
    """抽取中文二元词与英文词项，用于关键词召回。"""
    terms: list[str] = []
    for run in _CJK_RUN.findall(query):
        if len(run) <= 4:
            terms.append(run)
        else:
            terms.extend(run[index : index + 2] for index in range(len(run) - 1))
    terms.extend(_LATIN_TERM.findall(query))

    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = term.lower()
        if len(term) < 2 or normalized in _INTERROGATIVE_TERMS or normalized in seen:
            continue
        seen.add(normalized)
        result.append(term)
    return result[:max_terms]


def keyword_search(
    db: Session,
    *,
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    limit: int,
    document_ids: list[uuid.UUID] | None = None,
) -> list[uuid.UUID]:
    """PostgreSQL 关键词召回；按命中词项数量排序，不当作 BM25 分数。"""
    terms = extract_terms(query)
    if not terms:
        return []

    clauses = [
        Chunk.search_text.ilike(f"%{escape_like(term)}%", escape="\\") for term in terms
    ]
    hit_count = func.sum(case(*[(clause, 1) for clause in clauses], else_=0)).label("hits")
    conditions = [
        Collection.id == collection_id,
        Collection.user_id == user_id,
        Document.status == DOCUMENT_STATUS_READY,
        Document.deleted_at.is_(None),
        Document.is_enabled.is_(True),
        Document.is_current.is_(True),
        or_(*clauses),
    ]
    if document_ids is not None:
        conditions.append(Document.id.in_(document_ids))

    subquery = (
        select(
            Chunk.id.label("chunk_id"),
            Chunk.ordinal.label("ordinal"),
            hit_count,
        )
        .join(Document, Chunk.document_id == Document.id)
        .join(Collection, Document.collection_id == Collection.id)
        .where(*conditions)
        .group_by(Chunk.id, Chunk.ordinal)
        .subquery()
    )
    stmt = (
        select(subquery.c.chunk_id)
        .order_by(subquery.c.hits.desc(), subquery.c.ordinal.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())
