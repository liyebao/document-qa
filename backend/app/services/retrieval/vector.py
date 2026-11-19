import uuid

from pgvector.sqlalchemy import HALFVEC, VECTOR
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.orm import Session

from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import DOCUMENT_STATUS_READY, Document

# 迁移 0002 为这些维度建立了部分 HNSW 表达式索引。
# vector 类型 HNSW 上限 2000 维，3072 维使用 halfvec。
_ANN_VECTOR_DIMENSIONS = frozenset({768, 1024, 1536})
_ANN_HALFVEC_DIMENSIONS = frozenset({3072})


def _distance_and_dimension_filter(query_vector: list[float]):
    """选择与迁移中的表达式索引完全一致的写法，未命中维度时退回精确扫描。"""
    dimension = len(query_vector)
    if dimension in _ANN_VECTOR_DIMENSIONS:
        column = Chunk.embedding.cast(VECTOR(dimension))
        return column.cosine_distance(query_vector), func.vector_dims(
            Chunk.embedding
        ) == dimension
    if dimension in _ANN_HALFVEC_DIMENSIONS:
        column = Chunk.embedding.cast(HALFVEC(dimension))
        other = bindparam("query_vector_half", query_vector, type_=HALFVEC(dimension))
        return column.cosine_distance(other), func.vector_dims(
            Chunk.embedding
        ) == dimension
    return Chunk.embedding.cosine_distance(query_vector), None


def vector_search(
    db: Session,
    *,
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
    query_vector: list[float],
    limit: int,
    document_ids: list[uuid.UUID] | None = None,
) -> list[uuid.UUID]:
    """pgvector 语义检索；权限与文件状态在召回 SQL 中先行过滤。"""
    distance, dimension_filter = _distance_and_dimension_filter(query_vector)
    conditions = [
        Collection.id == collection_id,
        Collection.user_id == user_id,
        Document.status == DOCUMENT_STATUS_READY,
        Document.deleted_at.is_(None),
        Document.is_enabled.is_(True),
        Document.is_current.is_(True),
        Chunk.embedding.is_not(None),
    ]
    if dimension_filter is not None:
        conditions.append(dimension_filter)
    if document_ids is not None:
        conditions.append(Document.id.in_(document_ids))
    if len(query_vector) in _ANN_VECTOR_DIMENSIONS | _ANN_HALFVEC_DIMENSIONS:
        # 过滤条件较多时默认 ef_search=40 容易召回不足；只在命中 ANN 索引时调整，
        # 不影响精确扫描路径。
        db.execute(text("SET LOCAL hnsw.ef_search = 100"))
    stmt = (
        select(Chunk.id)
        .join(Document, Chunk.document_id == Document.id)
        .join(Collection, Document.collection_id == Collection.id)
        .where(*conditions)
        .order_by(distance)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())
