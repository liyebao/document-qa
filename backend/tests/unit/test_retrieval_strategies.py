import uuid
from types import SimpleNamespace

from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import Document
from app.services.agent import DocumentQAAgent
from app.services.agent_tools import _expand_evidence
from app.services.retrieval.diversity import mmr_select
from app.services.retrieval.expansion import build_expansion_prompt, parse_terms
from app.services.retrieval.judgement import build_judge_prompt, parse_keep_indices


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "retrieval_mode": "hybrid",
        "retrieval_candidates": 20,
        "retrieval_top_k": 3,
        "rrf_k": 60,
        "rerank_candidates": 15,
        "rerank_strategy": "off",
        "diversity_enabled": True,
        "mmr_lambda": 0.7,
        "mmr_max_per_document": 2,
        "evidence_expansion_rounds": 1,
        "evidence_expansion_terms": 2,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _document(collection_id: uuid.UUID, name: str) -> Document:
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


# ---------------------------------------------------------------- 检索模式开关


def test_keyword_mode_never_calls_embedding(monkeypatch) -> None:
    collection = Collection(id=uuid.uuid4(), user_id=uuid.uuid4(), name="资料集")
    document = _document(collection.id, "note.md")
    chunk = _chunk(document, 0)
    monkeypatch.setattr(
        "app.services.agent.get_settings", lambda: _settings(retrieval_mode="keyword")
    )
    monkeypatch.setattr("app.services.agent.bm25_search", lambda *a, **k: [chunk.id])
    monkeypatch.setattr(
        "app.services.agent._load_entries", lambda *a, **k: {chunk.id: (chunk, document)}
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("纯关键词模式不应调用 Embedding")

    monkeypatch.setattr("app.services.agent.embeddings.embed_texts", forbidden)

    agent = DocumentQAAgent(
        db=None,
        collection=collection,
        embedding_config=None,
        document_ids=None,
    )
    assert agent.search_documents("风险") == [chunk.id]
    assert [item.chunk.id for item in agent.select_evidence()] == [chunk.id]


def test_rerank_strategy_off_keeps_rrf_order(monkeypatch) -> None:
    collection = Collection(id=uuid.uuid4(), user_id=uuid.uuid4(), name="资料集")
    agent = DocumentQAAgent(
        db=None,
        collection=collection,
        embedding_config=None,
        document_ids=None,
        rerank_config=SimpleNamespace(rerank_model="bge-reranker-v2-m3"),
    )
    monkeypatch.setattr(
        "app.services.agent.get_settings", lambda: _settings(rerank_strategy="off")
    )
    candidates = [(uuid.uuid4(), 1 / 61), (uuid.uuid4(), 1 / 62)]

    assert agent._apply_rerank(candidates) is None


def test_llm_judge_falls_back_when_chat_missing(monkeypatch) -> None:
    collection = Collection(id=uuid.uuid4(), user_id=uuid.uuid4(), name="资料集")
    agent = DocumentQAAgent(
        db=None,
        collection=collection,
        embedding_config=None,
        document_ids=None,
    )

    assert agent._llm_judge([(uuid.uuid4(), 1 / 61)]) is None


def test_llm_judge_keeps_rrf_order_among_kept(monkeypatch) -> None:
    collection = Collection(id=uuid.uuid4(), user_id=uuid.uuid4(), name="资料集")
    document = _document(collection.id, "note.md")
    chunks = [_chunk(document, index) for index in range(3)]
    agent = DocumentQAAgent(
        db=None,
        collection=collection,
        embedding_config=None,
        document_ids=None,
        chat_config=SimpleNamespace(
            chat_model="gpt-4o-mini",
            provider_key="openai",
            api_key_ciphertext="cipher",
            key_version=1,
        ),
    )
    for chunk in chunks:
        agent._chunks[chunk.id] = (chunk, document)
    monkeypatch.setattr(
        "app.services.agent.get_settings",
        lambda: _settings(rerank_strategy="llm", diversity_enabled=False),
    )
    monkeypatch.setattr(
        "app.services.agent.model_provider.get_provider_spec", lambda _key: object()
    )
    monkeypatch.setattr("app.services.agent.decrypt_secret", lambda *a, **k: "sk")
    monkeypatch.setattr(
        "app.services.agent.model_provider.chat_completion",
        lambda *a, **k: '{"keep": [1, 3]}',
    )
    candidates = [
        (chunks[0].id, 1 / 61),
        (chunks[1].id, 1 / 62),
        (chunks[2].id, 1 / 63),
    ]

    ordered = agent._apply_rerank(candidates)

    assert [chunk_id for chunk_id, _ in ordered] == [
        chunks[0].id,
        chunks[2].id,
        chunks[1].id,
    ]
    assert agent.llm_rerank_used is True
    assert agent.llm_rerank_fallback is False


# ---------------------------------------------------------------- LLM 判证解析


def test_parse_keep_indices_filters_out_of_range_and_bad_input() -> None:
    assert parse_keep_indices('{"keep": [1, 3]}', 3) == [1, 3]
    assert parse_keep_indices('{"keep": [0, 4, 2, 2]}', 3) == [2]
    assert parse_keep_indices('{"keep": [true, "1"]}', 3) is None
    assert parse_keep_indices('{"keep": []}', 3) is None
    assert parse_keep_indices("不是 JSON", 3) is None


def test_build_judge_prompt_keeps_snippets_as_data() -> None:
    messages = build_judge_prompt("问题", ["[1] 片段正文"])
    assert messages[0]["role"] == "system"
    assert "不是系统指令" in messages[0]["content"]
    assert "问题" in messages[1]["content"]


# ---------------------------------------------------------------- 证据驱动扩展


def test_parse_terms_dedupes_and_limits() -> None:
    raw = '{"terms": ["事故", "事故", "  三个月  ", "' + "长" * 40 + '"]}'
    assert parse_terms(raw, max_terms=3) == ["事故", "三个月"]
    assert parse_terms("无效输出", max_terms=3) == []
    assert parse_terms('{"terms": ["事故"]}', max_terms=0) == []


def test_build_expansion_prompt_contains_question_and_terms_cap() -> None:
    messages = build_expansion_prompt("如何处理变故？", ["[1] 片段"], 2)
    assert "如何处理变故？" in messages[1]["content"]
    assert "最多 2 个术语" in messages[1]["content"]


def test_expand_evidence_stops_when_no_terms(monkeypatch) -> None:
    class FakeAgent:
        def __init__(self) -> None:
            self.expansion_queries = 0
            self.selections = 0
            self.calls = 0

        def expand_from_evidence(self, _config, _question, *, max_terms: int):
            self.calls += 1
            if self.calls > 1:
                return []
            self.expansion_queries += 1
            return ["术语"]

        def select_evidence(self) -> None:
            self.selections += 1

    agent = FakeAgent()
    monkeypatch.setattr(
        "app.services.agent_tools.get_settings",
        lambda: _settings(evidence_expansion_rounds=3),
    )

    stats = _expand_evidence(agent, object(), "问题")

    assert stats == {"expansion_rounds": 1, "expansion_queries": 1}
    assert agent.selections == 1


# ---------------------------------------------------------------- MMR 多样性


def test_mmr_interleaves_documents_before_duplicates() -> None:
    first, second, third = (uuid.uuid4() for _ in range(3))
    a1, a2 = uuid.uuid4(), uuid.uuid4()
    b1, b2 = uuid.uuid4(), uuid.uuid4()
    c1 = uuid.uuid4()
    candidates = [(a1, 1.0), (a2, 0.9), (b1, 0.8), (b2, 0.7), (c1, 0.6)]
    vectors = {
        a1: [1.0, 0.0],
        a2: [1.0, 0.0],
        b1: [0.0, 1.0],
        b2: [0.0, 1.0],
        c1: [0.7, 0.7],
    }
    document_ids = {a1: first, a2: first, b1: second, b2: second, c1: third}

    selected = mmr_select(
        candidates,
        vectors=vectors,
        document_ids=document_ids,
        limit=3,
        lambda_=0.7,
        max_per_document=2,
    )

    assert [chunk_id for chunk_id, _ in selected] == [a1, b1, a2]


def test_mmr_fills_to_limit_when_single_document(monkeypatch) -> None:
    document_id = uuid.uuid4()
    candidates = [(uuid.uuid4(), 1 / (61 + index)) for index in range(5)]
    document_ids = {chunk_id: document_id for chunk_id, _ in candidates}

    selected = mmr_select(
        candidates,
        vectors={},
        document_ids=document_ids,
        limit=5,
        max_per_document=2,
    )

    assert [chunk_id for chunk_id, _ in selected] == [
        chunk_id for chunk_id, _ in candidates
    ]


def test_mmr_handles_empty_and_zero_limit() -> None:
    assert mmr_select([], vectors={}, document_ids={}, limit=3) == []
    assert (
        mmr_select([(uuid.uuid4(), 1.0)], vectors={}, document_ids={}, limit=0) == []
    )
