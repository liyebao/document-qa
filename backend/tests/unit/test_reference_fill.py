import uuid
from types import SimpleNamespace

from app.models.chunk import Chunk
from app.models.collection import Collection
from app.models.document import Document
from app.services.agent import DocumentQAAgent, EvidenceItem
from app.services.retrieval import reference_fill


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "retrieval_mode": "hybrid",
        "retrieval_candidates": 20,
        "retrieval_top_k": 3,
        "rrf_k": 60,
        "rerank_candidates": 15,
        "rerank_strategy": "off",
        "diversity_enabled": False,
        "mmr_lambda": 0.7,
        "mmr_max_per_document": 2,
        "evidence_expansion_rounds": 0,
        "evidence_expansion_terms": 2,
        "reference_fill_enabled": True,
        "reference_fill_max_chunks": 6,
        "reference_fill_max_chars": 8000,
        "reference_fill_continuation_span": 1,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _document(name: str) -> Document:
    return Document(
        id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        filename=name,
        format="pdf",
        checksum=uuid.uuid4().hex,
        storage_path=f"/tmp/{uuid.uuid4()}.pdf",
    )


def _chunk(
    document: Document, text: str, *, fingerprint: str | None = None, ordinal: int = 0
) -> Chunk:
    return Chunk(
        id=uuid.uuid4(),
        document_id=document.id,
        fingerprint=fingerprint or uuid.uuid4().hex,
        ordinal=ordinal,
        text=text,
        search_text=text,
        heading_path="第一章",
    )


def _item(index: int, chunk: Chunk, document: Document) -> EvidenceItem:
    return EvidenceItem(
        index=index,
        chunk=chunk,
        document=document,
        rrf_score=1.0,
        query_indices={0},
    )


def _agent(evidence: list[EvidenceItem] | None = None) -> DocumentQAAgent:
    agent = DocumentQAAgent.__new__(DocumentQAAgent)
    agent.db = None
    agent.collection = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    agent.document_ids = None
    agent.reference_chunks = 0
    agent.evidence = evidence or []
    agent._chunks = {}
    agent._chunk_queries = {}
    agent.traces = []
    return agent


# ------------------------------------------------------------ 编号识别


def test_extract_references_from_mixed_question() -> None:
    labels = [
        reference.label
        for reference in reference_fill.extract_references("71条第2项、62条第2项、19条")
    ]
    assert labels == ["第七十一条", "第六十二条", "第十九条"]


def test_extract_references_accepts_chinese_and_chapters() -> None:
    labels = [
        reference.label
        for reference in reference_fill.extract_references("第十九条和第三章分别讲了什么")
    ]
    assert labels == ["第十九条", "第三章"]


def test_extract_references_accepts_numeric_sections() -> None:
    assert [
        reference.label
        for reference in reference_fill.extract_references("§3.2 讲了什么")
    ] == ["3.2"]
    assert [
        reference.label
        for reference in reference_fill.extract_references("第3.2节讲了什么")
    ] == ["3.2"]


def test_extract_references_ignores_counts_and_relative_phrases() -> None:
    assert reference_fill.extract_references("这份条例总共有多少条？") == []
    assert reference_fill.extract_references("共七十九条，最后一条是什么") == []
    assert reference_fill.extract_references("请列出全部章节") == []


def test_extract_references_dedupes_and_caps() -> None:
    assert [
        reference.label for reference in reference_fill.extract_references("第10条、第十条")
    ] == ["第十条"]
    labels = [
        reference.label
        for reference in reference_fill.extract_references("第一条第二条第三条第四条")
    ]
    assert labels == ["第一条", "第二条", "第三条"]


def test_reference_matching_skips_cross_references() -> None:
    article = reference_fill.extract_references("第三十九条")[0]
    assert article.matches("（二）违反本条例第三十九条规定造成财产损失") is False
    assert article.matches("第三十九条　基金会应当依法登记") is True


def test_section_matching_does_not_hit_longer_numbers() -> None:
    section = reference_fill.extract_references("3.2节")[0]
    assert section.matches("3.2 预算风险") is True
    assert section.matches("3.25 预算上限") is False


def test_needs_continuation_only_for_enumeration_lead_in() -> None:
    assert reference_fill.needs_continuation("业务主管单位履行下列监督管理职责：") is True
    assert reference_fill.needs_continuation("基金会应当依法登记。") is False
    assert reference_fill.needs_continuation("（一）伪造、变造登记证书；") is False
    # 页码页脚也不以句号结尾，但不能当成被截断的条文
    assert reference_fill.needs_continuation("第 19/27 页") is False


# ------------------------------------------------------ 按编号补证（同一条号）


def test_fill_missing_references_adds_same_article_from_other_document(
    monkeypatch,
) -> None:
    primary = _document("基金会管理条例.pdf")
    other = _document("中医药传统知识保护条例.pdf")
    primary_chunk = _chunk(primary, "第十九条　基金会终止前应当清算。")
    other_chunk = _chunk(other, "第十九条　建立中医药传统知识保护名录。")
    agent = _agent([_item(1, primary_chunk, primary)])
    agent._chunks[primary_chunk.id] = (primary_chunk, primary)
    agent._chunk_queries[primary_chunk.id] = {0}
    agent.traces = [
        SimpleNamespace(query_index=0, query="第十九条 基金会"),
        SimpleNamespace(query_index=1, query="第六十二条 第（二）项"),
    ]
    monkeypatch.setattr("app.services.agent.get_settings", lambda: _settings())
    monkeypatch.setattr(
        reference_fill,
        "fetch_reference_chunks",
        lambda *args, **kwargs: [(other_chunk, other)],
    )
    monkeypatch.setattr(reference_fill, "fetch_continuation_chunks", lambda *a, **k: [])

    added = agent.fill_missing_references("19条")

    assert added == 1
    assert agent.reference_chunks == 1
    assert agent.evidence[1].chunk is other_chunk
    assert agent.evidence[1].document is other
    # 补进来的内容要挂到问第十九条的那个子问题上，不能变成无主证据
    assert agent.evidence[1].query_indices == {0}


def test_fill_missing_references_fills_article_missing_from_same_document(
    monkeypatch,
) -> None:
    """同一文件里第六十二条已取到，不代表第七十一条也取到了。"""
    document = _document("基金会管理条例.pdf")
    chunk_62 = _chunk(document, "第六十二条　业务主管单位履行下列监督管理职责：", ordinal=18)
    chunk_71 = _chunk(
        document,
        "第七十一条　基金会有下列情形之一的，由登记管理机关责令限期改正：",
        ordinal=20,
    )
    agent = _agent([_item(1, chunk_62, document)])
    agent._chunks[chunk_62.id] = (chunk_62, document)
    agent._chunk_queries[chunk_62.id] = {0}
    agent.traces = [SimpleNamespace(query_index=1, query="第七十一条 第（二）项")]
    monkeypatch.setattr("app.services.agent.get_settings", lambda: _settings())
    monkeypatch.setattr(
        reference_fill, "fetch_reference_chunks", lambda *a, **k: [(chunk_71, document)]
    )
    monkeypatch.setattr(reference_fill, "fetch_continuation_chunks", lambda *a, **k: [])

    added = agent.fill_missing_references("第七十一条、第六十二条")

    assert added == 1
    assert agent.evidence[1].chunk is chunk_71
    assert agent.evidence[1].query_indices == {1}


def test_fill_missing_references_adds_following_chunk_for_enumerations(
    monkeypatch,
) -> None:
    """条号引导句和分项列举被分页切到两段时，两段都要取。"""
    document = _document("基金会管理条例.pdf")
    seed = _chunk(
        document,
        "第七十一条　基金会有下列情形之一的，由登记管理机关责令限期改正：",
        ordinal=20,
    )
    following = _chunk(
        document,
        "（二）违反本条例第三十九条规定造成基金会财产损失；",
        ordinal=21,
    )
    agent = _agent([_item(1, _chunk(document, "第十九条　清算。", ordinal=5), document)])
    agent.traces = [SimpleNamespace(query_index=2, query="第七十一条 第（二）项")]
    monkeypatch.setattr("app.services.agent.get_settings", lambda: _settings())
    monkeypatch.setattr(
        reference_fill, "fetch_reference_chunks", lambda *a, **k: [(seed, document)]
    )
    monkeypatch.setattr(
        reference_fill,
        "fetch_continuation_chunks",
        lambda *a, **k: [(following, document)],
    )

    added = agent.fill_missing_references("第七十一条")

    assert added == 2
    assert [item.chunk for item in agent.evidence[1:]] == [seed, following]
    # 后一段承接同一子问题，不能因为不含条号就变成无主证据
    assert agent.evidence[2].query_indices == {2}
    # 上下文要标出它接在哪一处依据后面，模型才知道这是同一条的后半段
    assert agent.evidence[2].continues == 2


def test_fill_missing_references_continues_truncated_enumeration_from_evidence(
    monkeypatch,
) -> None:
    """证据里的条号片段停在引导句冒号上时，也要补它的下一段。"""
    document = _document("基金会管理条例.pdf")
    lead = _chunk(document, "第六十二条　业务主管单位履行下列监督管理职责：", ordinal=18)
    items = _chunk(document, "（二）对基金会活动进行监督检查；", ordinal=19)
    agent = _agent([_item(1, lead, document)])
    agent._chunks[lead.id] = (lead, document)
    agent._chunk_queries[lead.id] = {0}
    monkeypatch.setattr("app.services.agent.get_settings", lambda: _settings())
    monkeypatch.setattr(
        reference_fill, "fetch_reference_chunks", lambda *a, **k: [(lead, document)]
    )
    captured: dict = {}

    def fake_continuation(*_args, **kwargs):
        captured.update(kwargs)
        return [(items, document)]

    monkeypatch.setattr(reference_fill, "fetch_continuation_chunks", fake_continuation)

    added = agent.fill_missing_references("第六十二条")

    assert added == 1
    assert captured["seeds"] == [(document.id, 18)]
    assert agent.evidence[1].chunk is items
    assert agent.evidence[1].query_indices == {0}
    assert agent.evidence[1].continues == 1


def test_item_question_forces_article_window(monkeypatch) -> None:
    """问「第X项」时，整条原文可能跨多个片段，必须按窗口取而不是只看冒号。"""
    document = _document("基金会管理条例.pdf")
    lead = _chunk(document, "第三十三条　监事会、监事依法行使章程规定的下列职权", ordinal=9)
    agent = _agent([_item(1, lead, document)])
    monkeypatch.setattr("app.services.agent.get_settings", lambda: _settings())
    monkeypatch.setattr(reference_fill, "fetch_reference_chunks", lambda *a, **k: [])
    captured: dict = {}

    def fake_continuation(*_args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(reference_fill, "fetch_continuation_chunks", fake_continuation)

    agent.fill_missing_references("第33条第3项")

    assert captured["span"] == 2
    assert captured["seeds"] == [(document.id, 9)]


def test_fill_missing_references_honours_continuation_span(monkeypatch) -> None:
    document = _document("基金会管理条例.pdf")
    lead = _chunk(document, "第七十一条　基金会有下列情形之一的：", ordinal=20)
    agent = _agent([_item(1, lead, document)])
    monkeypatch.setattr(
        "app.services.agent.get_settings",
        lambda: _settings(reference_fill_continuation_span=2),
    )
    monkeypatch.setattr(reference_fill, "fetch_reference_chunks", lambda *a, **k: [])
    captured: dict = {}

    def fake_continuation(*_args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(reference_fill, "fetch_continuation_chunks", fake_continuation)

    agent.fill_missing_references("第七十一条")

    assert captured["span"] == 2


def test_fill_missing_references_disabled_by_settings(monkeypatch) -> None:
    agent = _agent([_item(1, _chunk(_document("a.pdf"), "第十九条　清算。"), _document("a.pdf"))])
    monkeypatch.setattr(
        "app.services.agent.get_settings",
        lambda: _settings(reference_fill_enabled=False),
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("关闭补全后不应查库")

    monkeypatch.setattr(reference_fill, "fetch_reference_chunks", forbidden)

    assert agent.fill_missing_references("第十九条") == 0


def test_fill_missing_references_skips_articles_already_in_evidence(monkeypatch) -> None:
    primary = _document("基金会管理条例.pdf")
    other = _document("中医药条例.pdf")
    primary_chunk = _chunk(primary, "第十九条　基金会终止前应当清算。")
    other_chunk = _chunk(other, "第十九条　建立保护名录。")
    agent = _agent(
        [_item(1, primary_chunk, primary), _item(2, other_chunk, other)]
    )
    monkeypatch.setattr("app.services.agent.get_settings", lambda: _settings())
    monkeypatch.setattr(
        reference_fill,
        "fetch_reference_chunks",
        lambda *a, **k: [(primary_chunk, primary), (other_chunk, other)],
    )

    assert agent.fill_missing_references("第十九条") == 0


def test_fill_missing_references_without_reference_does_not_query(monkeypatch) -> None:
    agent = _agent([_item(1, _chunk(_document("a.pdf"), "正文"), _document("a.pdf"))])
    monkeypatch.setattr("app.services.agent.get_settings", lambda: _settings())

    def forbidden(*_args, **_kwargs):
        raise AssertionError("没有编号时不应补证")

    monkeypatch.setattr(reference_fill, "fetch_reference_chunks", forbidden)

    assert agent.fill_missing_references("这份条例总共有多少条？") == 0


# ------------------------------------------------- 同文多文件（指纹相同）


def test_select_evidence_records_other_document_with_same_content(monkeypatch) -> None:
    collection = Collection(id=uuid.uuid4(), user_id=uuid.uuid4(), name="资料集")
    first = _document("基金会管理条例.pdf")
    second = _document("基金会管理条例.md")
    fingerprint = "f" * 64
    first_chunk = _chunk(first, "第十九条　基金会终止前应当清算。", fingerprint=fingerprint)
    second_chunk = _chunk(
        second, "第十九条　基金会终止前应当清算。", fingerprint=fingerprint
    )
    agent = DocumentQAAgent(
        db=None, collection=collection, embedding_config=None, document_ids=None
    )
    agent._ranked_lists = [[first_chunk.id, second_chunk.id]]
    agent._chunks = {
        first_chunk.id: (first_chunk, first),
        second_chunk.id: (second_chunk, second),
    }
    agent._chunk_queries = {first_chunk.id: {0}, second_chunk.id: {0}}
    monkeypatch.setattr("app.services.agent.get_settings", lambda: _settings())

    evidence = agent.select_evidence()

    assert len(evidence) == 1
    assert evidence[0].chunk is first_chunk
    assert evidence[0].also_in == {"基金会管理条例.md"}


def test_build_context_marks_same_content_in_other_file() -> None:
    document = _document("基金会管理条例.pdf")
    chunk = _chunk(document, "第十九条　基金会终止前应当清算。")
    item = _item(1, chunk, document)
    item.also_in.add("基金会管理条例.md")
    agent = _agent([item])

    context = agent.build_context()

    assert "同文另见" in context
    assert "基金会管理条例.md" in context


def test_build_context_links_page_split_halves() -> None:
    """条号引导句与分项列举被切成两段时，上下文要标出它们的上下关系。"""
    document = _document("基金会管理条例.pdf")
    lead = _chunk(document, "第七十一条　基金会有下列情形之一的：", ordinal=20)
    items = _chunk(document, "（二）违反本条例第三十九条规定造成基金会财产损失；", ordinal=21)
    agent = _agent([_item(1, lead, document), _item(2, items, document)])

    context = agent.build_context()

    assert "下文见：[2]" in context
    assert "紧接上文：[1]" in context


def test_full_document_expansion_marks_duplicate_from_other_file(monkeypatch) -> None:
    from app.services.retrieval import full_doc

    primary = _document("基金会管理条例.pdf")
    other = _document("基金会管理条例.md")
    fingerprint = "a" * 64
    primary_chunk = _chunk(primary, "第十九条　基金会终止前应当清算。", fingerprint=fingerprint)
    duplicate = _chunk(other, "第十九条　基金会终止前应当清算。", fingerprint=fingerprint)
    agent = _agent([_item(1, primary_chunk, primary)])
    agent.full_scan_chunks = 0
    agent._chunks[primary_chunk.id] = (primary_chunk, primary)
    agent._chunk_queries[primary_chunk.id] = {0}
    monkeypatch.setattr(
        full_doc, "fetch_document_chunks", lambda *args, **kwargs: [(duplicate, other)]
    )

    added = agent.expand_evidence_for_full_document()

    assert added == 0
    assert agent.evidence[0].also_in == {"基金会管理条例.md"}
