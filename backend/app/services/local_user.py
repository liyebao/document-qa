from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import USER_STATUS_ACTIVE, User

LOCAL_USER_EMAIL = "local@localhost"


def get_local_user(db: Session) -> User:
    """单用户模式：复用已有用户以保留历史资料；首次启动时创建本地用户。"""
    user = db.scalar(select(User).order_by(User.created_at.asc(), User.id.asc()).limit(1))
    if user is not None:
        return user

    user = User(email=LOCAL_USER_EMAIL, status=USER_STATUS_ACTIVE)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # 并发首次请求时可能同时创建，回滚后读取已存在的那一条。
        db.rollback()
        existing = db.scalar(
            select(User).order_by(User.created_at.asc(), User.id.asc()).limit(1)
        )
        if existing is None:
            raise
        return existing
    db.refresh(user)
    return user


def ensure_local_user() -> User:
    with SessionLocal() as db:
        return get_local_user(db)
