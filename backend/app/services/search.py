from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.text_utils import escape_like
from app.models.collection import Collection
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.user import User
from app.schemas.search import SearchItem
from app.services.conversations import conversation_activity_column


def _contains(term: str) -> str:
    return f"%{escape_like(term)}%"


def _search_conversations(
    db: Session, user: User, term: str, limit: int
) -> list[SearchItem]:
    """标题模糊匹配，按「最近活动时间」倒序；活动时间与侧边栏列表同一表达式。"""
    activity = conversation_activity_column().label("updated_at")
    stmt = (
        select(
            Conversation.id,
            Conversation.title,
            Conversation.collection_id,
            Collection.name.label("collection_name"),
            activity,
        )
        .join(Collection, Collection.id == Conversation.collection_id)
        .where(
            Conversation.user_id == user.id,
            Conversation.title.ilike(_contains(term), escape="\\"),
        )
        .order_by(activity.desc(), Conversation.id.desc())
        .limit(limit)
    )
    return [
        SearchItem(
            kind="conversation",
            id=row.id,
            label=row.title,
            sublabel=row.collection_name,
            collection_id=row.collection_id,
            collection_name=row.collection_name,
        )
        for row in db.execute(stmt).all()
    ]


def _search_documents(db: Session, user: User, term: str, limit: int) -> list[SearchItem]:
    """文件名模糊匹配，只含未删除资料。

    文档没有单独的 title 列：粘贴文本与网页入库时都会把标题折进文件名
    （`<title>.txt` / markdown 文件名），所以匹配 filename 即覆盖标题语义。
    """
    stmt = (
        select(
            Document.id,
            Document.filename,
            Document.collection_id,
            Collection.name.label("collection_name"),
        )
        .join(Collection, Collection.id == Document.collection_id)
        .where(
            Collection.user_id == user.id,
            Document.deleted_at.is_(None),
            Document.filename.ilike(_contains(term), escape="\\"),
        )
        .order_by(Document.created_at.desc(), Document.id.desc())
        .limit(limit)
    )
    return [
        SearchItem(
            kind="document",
            id=row.id,
            label=row.filename,
            sublabel=row.collection_name,
            collection_id=row.collection_id,
            collection_name=row.collection_name,
        )
        for row in db.execute(stmt).all()
    ]


def _search_collections(db: Session, user: User, term: str, limit: int) -> list[SearchItem]:
    stmt = (
        select(Collection.id, Collection.name)
        .where(
            Collection.user_id == user.id,
            Collection.name.ilike(_contains(term), escape="\\"),
        )
        .order_by(Collection.created_at.desc(), Collection.id.desc())
        .limit(limit)
    )
    return [
        SearchItem(
            kind="collection",
            id=row.id,
            label=row.name,
            sublabel=None,
            collection_id=row.id,
            collection_name=row.name,
        )
        for row in db.execute(stmt).all()
    ]


def search_all(db: Session, user: User, term: str, per_kind: int) -> list[SearchItem]:
    """三类各一条 LIMIT 查询，固定 3 次往返，与命中条数无关。"""
    return [
        *_search_conversations(db, user, term, per_kind),
        *_search_documents(db, user, term, per_kind),
        *_search_collections(db, user, term, per_kind),
    ]
