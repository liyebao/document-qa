from app.services.retrieval.keyword import escape_like, extract_terms


def test_extract_terms_from_chinese_and_latin() -> None:
    terms = extract_terms("RAG 系统的检索召回效果如何")
    assert "RAG" in terms
    assert "检索" in terms
    assert "如何" not in terms


def test_extract_terms_respects_limit() -> None:
    terms = extract_terms("这是一个用于测试关键词抽取长度限制的很长很长的问题句子", max_terms=5)
    assert len(terms) == 5


def test_extract_terms_empty_query() -> None:
    assert extract_terms("，。！？") == []


def test_escape_like_treats_wildcards_as_literal_text() -> None:
    assert escape_like("100%_done") == "100\\%\\_done"
    assert escape_like("a\\b") == "a\\\\b"
