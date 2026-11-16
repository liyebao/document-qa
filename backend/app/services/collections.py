import uuid

from sqlalchemy import and_, bindparam, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import DOCUMENT_STATUS_READY, Document
from app.models.user import User
from app.schemas.collection import CollectionSummary
from app.services import embeddings, model_provider
from app.services.parsers.base import normalize_text
from app.services.storage import delete_stored_file


def list_collections(db: Session, user: User) -> list[CollectionSummary]:
    stmt = (
        select(Collection, func.count(Document.id))
        .outerjoin(
            Document,
            and_(
                Document.collection_id == Collection.id,
                Document.deleted_at.is_(None),
                Document.is_current.is_(True),
                Document.is_enabled.is_(True),
            ),
        )
        .where(Collection.user_id == user.id)
        .group_by(Collection.id)
        .order_by(Collection.created_at.desc())
    )
    return [
        CollectionSummary(
            id=collection.id,
            name=collection.name,
            embedding_provider=collection.embedding_provider,
            embedding_model=collection.embedding_model,
            embedding_dimension=collection.embedding_dimension,
            index_version=collection.index_version,
            created_at=collection.created_at,
            document_count=count,
        )
        for collection, count in db.execute(stmt).all()
    ]


def create_collection(db: Session, user: User, name: str) -> Collection:
    collection = Collection(user_id=user.id, name=normalize_text(name))
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


def rename_collection(db: Session, collection: Collection, name: str) -> Collection:
    collection.name = normalize_text(name)
    db.commit()
    db.refresh(collection)
    return collection


def delete_collection(db: Session, collection: Collection) -> None:
    paths = list(
        db.scalars(
            select(Document.storage_path).where(Document.collection_id == collection.id)
        ).all()
    )
    db.delete(collection)
    db.commit()
    for path in paths:
        delete_stored_file(path)


def reindex_collection(
    db: Session, collection: Collection, provider_key: str | None
) -> tuple[Collection, int]:
    """用当前 Embedding 配置重算资料集全部片段向量。

    先完成全部向量请求再写库，失败时旧索引保持不变；成功后递增
    index_version，使新旧向量空间不会混用。
    """
    locked = db.scalar(
        select(func.pg_try_advisory_xact_lock(func.hashtext(str(collection.id))))
    )
    if not locked:
        raise AppError("REINDEX_IN_PROGRESS", "该资料集正在重建索引，请稍后再试", 409)

    if provider_key:
        config = model_provider.get_user_config(db, collection.user_id, provider_key)
        if config is None:
            raise AppError(
                "MODEL_NOT_CONFIGURED", "尚未配置该服务商，请先在模型设置中保存", 422
            )
    else:
        config = model_provider.preferred_embedding_config(db, collection.user_id)
    if config is None or not config.embedding_model:
        raise AppError(
            "MODEL_NOT_CONFIGURED",
            "请先在模型设置中配置支持 Embedding 的服务商（如 OpenAI、百炼或硅基流动）",
            422,
        )

    chunks = list(
        db.scalars(
            select(Chunk)
            .join(Document, Chunk.document_id == Document.id)
            .where(
                Document.collection_id == collection.id,
                Document.status == DOCUMENT_STATUS_READY,
                Document.deleted_at.is_(None),
                Document.is_current.is_(True),
            )
            .order_by(Chunk.document_id, Chunk.ordinal)
        ).all()
    )
    if not chunks:
        raise AppError(
            "REINDEX_EMPTY", "当前资料集没有可重建索引的片段，请先上传并处理文件", 409
        )

    vectors = embeddings.embed_texts(
        config, [chunk.search_text or chunk.text for chunk in chunks]
    )
    if len(vectors) != len(chunks):
        raise AppError("MODEL_PROVIDER_ERROR", "Embedding 返回数量与片段数量不一致", 502)
    dimension = len(vectors[0]) if vectors else 0
    if dimension == 0 or any(len(vector) != dimension for vector in vectors):
        raise AppError("MODEL_PROVIDER_ERROR", "Embedding 返回的向量维度不一致", 502)

    # 用 Core UPDATE 写入新向量，避免 ORM 在刷新时比较不同维度的旧/新向量。
    # 一次 executemany 提交全部行：逐条 execute 在 5000 片段时会产生 5000 次往返，
    # 期间一直占着 advisory lock 和一个长事务。
    # 必须对 __table__ 构造 UPDATE：传 ORM 实体时 Session.execute 会走
    # “按主键批量更新”分支，要求参数字典里带 id 字段，否则直接报错。
    chunk_table = Chunk.__table__
    db.execute(
        chunk_table.update()
        .where(chunk_table.c.id == bindparam("chunk_id"))
        .values(embedding=bindparam("chunk_embedding")),
        [
            {"chunk_id": chunk.id, "chunk_embedding": vector}
            for chunk, vector in zip(chunks, vectors, strict=True)
        ],
    )
    collection.embedding_provider = config.provider_key
    collection.embedding_model = config.embedding_model
    collection.embedding_dimension = dimension
    collection.index_version = (collection.index_version or 0) + 1
    db.commit()
    db.refresh(collection)
    return collection, len(chunks)


def get_collection_or_error(
    db: Session, collection_id: uuid.UUID, user: User
) -> Collection:
    collection = db.scalar(
        select(Collection).where(
            Collection.id == collection_id, Collection.user_id == user.id
        )
    )
    if collection is None:
        raise AppError("NOT_FOUND", "资料集不存在", 404)
    return collection
