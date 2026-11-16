from app.services.retrieval.bm25 import bm25_score
from app.services.retrieval.tokenizer import tokenize


def test_tokenize_keeps_meaningful_terms() -> None:
    terms = tokenize("RAG 检索增强生成系统的召回效果如何")

    assert "rag" in terms
    assert any("检索" in term for term in terms)
    assert "如何" not in terms


def test_tokenize_drops_single_characters_and_punctuation() -> None:
    assert tokenize("，。！？ a 我") == []


def test_bm25_score_rewards_higher_term_frequency() -> None:
    low = bm25_score(tf=1, df=2, doc_count=10, doc_len=100, avg_len=100)
    high = bm25_score(tf=5, df=2, doc_count=10, doc_len=100, avg_len=100)

    assert high > low > 0


def test_bm25_score_penalizes_long_documents() -> None:
    short = bm25_score(tf=2, df=2, doc_count=10, doc_len=100, avg_len=100)
    long = bm25_score(tf=2, df=2, doc_count=10, doc_len=1000, avg_len=100)

    assert short > long


def test_bm25_score_handles_missing_terms() -> None:
    assert bm25_score(tf=0, df=1, doc_count=10, doc_len=10, avg_len=10) == 0.0
    assert bm25_score(tf=1, df=0, doc_count=10, doc_len=10, avg_len=10) == 0.0
