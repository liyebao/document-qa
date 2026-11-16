"""BM25 关键词召回：倒排表 + 文档频率，替换原来的子串命中计数。"""

import math
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.retrieval.tokenizer import tokenize

BM25_K1 = 1.5
BM25_B = 0.75
MAX_QUERY_TERMS = 24

# 只统计当前用户、当前资料集内可检索的片段，保证 df 与召回范围一致。
_SQL = text(
    """
    WITH scoped AS (
        SELECT c.id AS chunk_id, c.token_count AS dl
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        JOIN collections col ON col.id = d.collection_id
        WHERE col.id = :collection_id
          AND col.user_id = :user_id
          AND d.status = 'ready'
          AND d.is_current = TRUE
          AND d.is_enabled = TRUE
          AND d.deleted_at IS NULL
          AND c.token_count > 0
          AND (
              CAST(:document_ids AS uuid[]) IS NULL
              OR d.id = ANY(CAST(:document_ids AS uuid[]))
          )
    ),
    stats AS (
        SELECT COUNT(*)::float AS n, GREATEST(AVG(dl), 1) AS avgdl FROM scoped
    ),
    q AS (
        SELECT DISTINCT term FROM unnest(CAST(:terms AS text[])) AS term
    ),
    df AS (
        SELECT ct.term, COUNT(DISTINCT ct.chunk_id)::float AS df
        FROM chunk_terms ct
        JOIN scoped s ON s.chunk_id = ct.chunk_id
        JOIN q ON q.term = ct.term
        GROUP BY ct.term
    )
    SELECT s.chunk_id,
           SUM(
               ln(1 + (st.n - df.df + 0.5) / (df.df + 0.5))
               * (ct.tf * (:k1 + 1))
               / (ct.tf + :k1 * (1 - :b + :b * s.dl / st.avgdl))
           ) AS score
    FROM scoped s
    JOIN chunk_terms ct ON ct.chunk_id = s.chunk_id
    JOIN df ON df.term = ct.term
    CROSS JOIN stats st
    GROUP BY s.chunk_id
    ORDER BY score DESC, s.chunk_id ASC
    LIMIT :limit
    """
)


def bm25_score(
    tf: float,
    df: float,
    doc_count: float,
    doc_len: float,
    avg_len: float,
    *,
    k1: float = BM25_K1,
    b: float = BM25_B,
) -> float:
    """标准 BM25 打分；口径与 SQL 中完全一致，便于测试对照。"""
    if tf <= 0 or df <= 0 or doc_count <= 0:
        return 0.0
    idf = math.log(1 + (doc_count - df + 0.5) / (df + 0.5))
    normalizer = 1 - b + b * doc_len / max(avg_len, 1e-9)
    return idf * (tf * (k1 + 1)) / (tf + k1 * normalizer)


def bm25_search(
    db: Session,
    *,
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    limit: int,
    document_ids: list[uuid.UUID] | None = None,
) -> list[uuid.UUID]:
    terms = list(dict.fromkeys(tokenize(query)))[:MAX_QUERY_TERMS]
    if not terms:
        return []
    rows = db.execute(
        _SQL,
        {
            "collection_id": collection_id,
            "user_id": user_id,
            "terms": terms,
            "document_ids": document_ids,
            "k1": BM25_K1,
            "b": BM25_B,
            "limit": limit,
        },
    ).all()
    return [row[0] for row in rows]
