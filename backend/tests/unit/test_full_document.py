from types import SimpleNamespace
from uuid import uuid4

from app.services.agent import DocumentQAAgent, EvidenceItem
from app.services.retrieval import full_doc


def _chunk(text: str = "原文内容"):
    return SimpleNamespace(
        id=uuid4(),
        text=text,
        fingerprint=None,
        heading_path="第1章",
        page_start=1,
        page_end=None,
        ordinal=1,
    )


def _document():
    return SimpleNamespace(id=uuid4(), filename="资料.pdf")


def test_needs_full_document_detects_count_questions() -> None:
    assert full_doc.needs_full_document("这份文件总共有多少条？")
    assert full_doc.needs_full_document("请列出全部章节")
    assert full_doc.needs_full_document("最后一条是什么")
    assert not full_doc.needs_full_document("第 3 页讲了什么")


def test_expand_evidence_for_full_document_appends_missing_chunks(monkeypatch) -> None:
    chunk = _chunk()
    new_chunk = _chunk("后续内容")
    document = _document()
    agent = DocumentQAAgent.__new__(DocumentQAAgent)
    agent.db = None
    agent.collection = SimpleNamespace(id=uuid4())
    agent.full_scan_chunks = 0
    agent.evidence = [
        EvidenceItem(
            index=1, chunk=chunk, document=document, rrf_score=1.0, query_indices={0}
        )
    ]
    agent._chunks = {}
    agent._chunk_queries = {}
    monkeypatch.setattr(
        full_doc,
        "fetch_document_chunks",
        lambda *args, **kwargs: [(chunk, document), (new_chunk, document)],
    )
    monkeypatch.setattr(
        "app.services.agent.get_settings",
        lambda: SimpleNamespace(full_scan_max_chunks=10, full_scan_max_chars=24000),
    )

    added = agent.expand_evidence_for_full_document()

    assert added == 1
    assert len(agent.evidence) == 2
    assert agent.evidence[1].index == 2
    assert agent.evidence[1].chunk is new_chunk
    assert agent.evidence[1].query_indices == {-1}


def test_build_context_uses_neutral_source_labels() -> None:
    chunk = _chunk()
    document = _document()
    agent = DocumentQAAgent.__new__(DocumentQAAgent)
    agent.db = None
    agent.collection = SimpleNamespace(id=uuid4())
    agent.full_scan_chunks = 0
    agent.evidence = [
        EvidenceItem(
            index=1, chunk=chunk, document=document, rrf_score=1.0, query_indices={0}
        )
    ]

    context = agent.build_context()

    assert "原文内容" in context
    assert "资料.pdf" in context
    assert "片段" not in context
