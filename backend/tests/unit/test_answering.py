import uuid

from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import Document
from app.services.answering import DocumentQAAgent


def _document(collection_id: uuid.UUID, name: str = "note.md") -> Document:
    return Document(
        id=uuid.uuid4(),
        collection_id=collection_id,
        filename=name,
        format="md",
        checksum=uuid.uuid4().hex,
        storage_path=f"/tmp/{uuid.uuid4()}.md",
    )


def _chunk(document: Document, ordinal: int) -> Chunk:
    return Chunk(
        id=uuid.uuid4(),
        document_id=document.id,
        fingerprint=uuid.uuid4().hex,
        ordinal=ordinal,
        text=f"片段 {ordinal}",
        search_text=f"片段 {ordinal}",
    )


def _agent(collection: Collection) -> DocumentQAAgent:
    return DocumentQAAgent(
        db=None,  # 选择逻辑不访问数据库
        collection=collection,
        embedding_config=None,  # 选择逻辑不调用模型
        document_ids=None,
    )


def test_select_evidence_limits_context_and_reports_coverage() -> None:
    collection = Collection(id=uuid.uuid4(), user_id=uuid.uuid4(), name="测试资料集")
    document = _document(collection.id)
    agent = _agent(collection)
    chunks = [_chunk(document, ordinal) for ordinal in range(7)]
    for chunk in chunks:
        agent._chunks[chunk.id] = (chunk, document)
    ranked = [chunk.id for chunk in chunks]
    agent._ranked_lists = [ranked, ranked]
    for index, chunk in enumerate(chunks):
        agent._chunk_queries[chunk.id] = {0} if index < 5 else {1}

    evidence = agent.select_evidence()

    assert len(evidence) == 5
    assert [item.index for item in evidence] == [1, 2, 3, 4, 5]
    assert agent.coverage(2) == [True, False]


def test_select_evidence_with_no_candidates() -> None:
    collection = Collection(id=uuid.uuid4(), user_id=uuid.uuid4(), name="空资料集")
    agent = _agent(collection)

    assert agent.select_evidence() == []
    assert agent.coverage(2) == [False, False]
