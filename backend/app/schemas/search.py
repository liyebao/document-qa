import uuid
from typing import Literal

from pydantic import BaseModel

SearchKind = Literal["conversation", "document", "collection"]


class SearchItem(BaseModel):
    """全局搜索的一条命中：kind 决定前端跳转目标，label/sublabel 只用于展示。"""

    kind: SearchKind
    id: uuid.UUID
    label: str
    sublabel: str | None = None
    collection_id: uuid.UUID | None = None
    collection_name: str | None = None


class SearchResponse(BaseModel):
    items: list[SearchItem] = []
