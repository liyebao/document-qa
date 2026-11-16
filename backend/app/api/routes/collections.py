
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, reindex_rate_limit, require_collection
from app.db.session import get_db
from app.models.collection import Collection
from app.models.user import User
from app.schemas.collection import (
    CollectionCreate,
    CollectionOut,
    CollectionReindexOut,
    CollectionReindexRequest,
    CollectionSummary,
    CollectionUpdate,
)
from app.schemas.conversation import ConversationCreate, ConversationOut
from app.services import collections, conversations

router = APIRouter(prefix="/api/collections", tags=["collections"])


@router.get("", response_model=list[CollectionSummary])
def list_collections(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CollectionSummary]:
    return collections.list_collections(db, user)


@router.post("", response_model=CollectionOut, status_code=201)
def create_collection(
    payload: CollectionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CollectionOut:
    collection = collections.create_collection(db, user, payload.name)
    return CollectionOut.model_validate(collection)


@router.get("/{collection_id}", response_model=CollectionOut)
def get_collection(collection: Collection = Depends(require_collection)) -> CollectionOut:
    return CollectionOut.model_validate(collection)


@router.patch("/{collection_id}", response_model=CollectionOut)
def rename_collection(
    payload: CollectionUpdate,
    collection: Collection = Depends(require_collection),
    db: Session = Depends(get_db),
) -> CollectionOut:
    updated = collections.rename_collection(db, collection, payload.name)
    return CollectionOut.model_validate(updated)


@router.delete("/{collection_id}", status_code=204)
def delete_collection(
    collection: Collection = Depends(require_collection), db: Session = Depends(get_db)
) -> Response:
    collections.delete_collection(db, collection)
    return Response(status_code=204)


@router.post("/{collection_id}/reindex", response_model=CollectionReindexOut)
def reindex_collection(
    payload: CollectionReindexRequest,
    collection: Collection = Depends(require_collection),
    db: Session = Depends(get_db),
    _: None = Depends(reindex_rate_limit),
) -> CollectionReindexOut:
    updated, chunk_count = collections.reindex_collection(
        db, collection, payload.provider_key
    )
    return CollectionReindexOut(
        **CollectionOut.model_validate(updated).model_dump(),
        chunk_count=chunk_count,
    )


@router.get("/{collection_id}/conversations", response_model=list[ConversationOut])
def list_conversations(
    collection: Collection = Depends(require_collection), db: Session = Depends(get_db)
) -> list[ConversationOut]:
    return [
        ConversationOut.model_validate(item)
        for item in conversations.list_conversations(db, collection)
    ]


@router.post("/{collection_id}/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    collection: Collection = Depends(require_collection),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationOut:
    conversation = conversations.create_conversation(db, user, collection, payload.title)
    return ConversationOut.model_validate(conversation)
