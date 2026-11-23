from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.user import User
from app.schemas.search import SearchResponse
from app.services import search as search_service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search_knowledge_base(
    q: str = Query(min_length=1, max_length=100),
    per_kind: int = Query(default=5, ge=1, le=10),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """会话标题 / 文档名 / 资料集名的全局模糊搜索。

    只按当前用户的数据检索；每类各取 per_kind 条，总查询数固定为 3。
    """
    term = q.strip()
    if not term:
        # 纯空白能通过 min_length=1，这里显式挡掉，统一走 AppError 的错误码风格。
        raise AppError("VALIDATION_ERROR", "搜索关键词不能为空", 422)
    return SearchResponse(items=search_service.search_all(db, user, term, per_kind))
