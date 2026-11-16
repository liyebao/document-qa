import json
import math
import sys
from pathlib import Path

import pytest

EVALUATION_DIR = Path(__file__).resolve().parents[3] / "evaluation"
if str(EVALUATION_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_DIR))

from analyze_traces import (  # noqa: E402
    attach_retrieval,
    load_traces,
    ranked_values,
    strategy_groups,
)
from metrics import (  # noqa: E402
    first_relevant_rank,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    retrieval_mrr,
    retrieval_ndcg_at_k,
    retrieval_recall_at_k,
)


def test_recall_and_mrr_at_rank() -> None:
    ranked = ["a.pdf", "b.pdf", "c.pdf"]
    assert first_relevant_rank(ranked, ["c.pdf"]) == 3
    assert recall_at_k(ranked, ["c.pdf"], 2) == 0.0
    assert recall_at_k(ranked, ["c.pdf"], 3) == 1.0
    assert reciprocal_rank(ranked, ["b.pdf"]) == 0.5
    assert recall_at_k(ranked, [], 5) is None


def test_ndcg_rewards_higher_rank() -> None:
    assert ndcg_at_k(["a.pdf", "b.pdf"], ["a.pdf"], 2) == pytest.approx(1.0)
    assert ndcg_at_k(["a.pdf", "b.pdf"], ["b.pdf"], 2) == pytest.approx(
        1 / math.log2(3)
    )
    assert ndcg_at_k(["a.pdf", "b.pdf"], ["c.pdf"], 2) == pytest.approx(0.0)
    assert ndcg_at_k(["a.pdf"], [], 5) is None


def test_retrieval_ndcg_ignores_cases_without_labels() -> None:
    records = [
        {"retrieved_documents": ["a.pdf", "b.pdf"], "expected_files": ["b.pdf"]},
        {"retrieved_documents": ["c.pdf"], "expected_files": ["d.pdf"]},
        {"retrieved_documents": ["e.pdf"], "expected_files": []},
    ]
    # 第一题命中在第 2 名，第二题未命中；无标注的第三题不参与平均。
    expected = (1 / math.log2(3)) / 2
    assert retrieval_ndcg_at_k(records, 5) == pytest.approx(expected)


def test_retrieval_metrics_ignore_cases_without_labels() -> None:
    records = [
        {"retrieved_documents": ["a.pdf", "b.pdf"], "expected_files": ["b.pdf"]},
        {"retrieved_documents": ["c.pdf"], "expected_files": ["d.pdf"]},
        {"retrieved_documents": ["e.pdf"], "expected_files": []},
    ]
    assert retrieval_recall_at_k(records, 5) == 0.5
    assert retrieval_mrr(records) == 0.25


def test_ranked_values_deduplicates_and_keeps_order() -> None:
    traces = [
        {
            "searches": [
                {
                    "fused": [
                        {"chunk_id": "c1", "document_name": "a.pdf"},
                        {"chunk_id": "c2", "document_name": "b.pdf"},
                    ]
                },
                {
                    "fused": [
                        {"chunk_id": "c2", "document_name": "b.pdf"},
                        {"chunk_id": "c3", "document_name": "a.pdf"},
                    ]
                },
            ]
        }
    ]
    documents, chunks = ranked_values(traces)
    assert documents == ["a.pdf", "b.pdf"]
    assert chunks == ["c1", "c2", "c3"]


def test_load_traces_and_attach_retrieval(tmp_path: Path) -> None:
    log_path = tmp_path / "backend.log"
    payload = {
        "conversation_id": "conv-1",
        "searches": [
            {
                "fused": [
                    {"chunk_id": "c1", "document_name": "a.pdf"},
                ]
            }
        ],
    }
    log_path.write_text(
        "2026-01-01 INFO retrieval_trace "
        + json.dumps(payload, ensure_ascii=False)
        + "\n普通日志\n",
        encoding="utf-8",
    )

    traces = load_traces(log_path)
    records = [
        {"conversation_id": "conv-1", "expected_files": ["a.pdf"]},
        {"conversation_id": "conv-2", "expected_files": ["b.pdf"]},
    ]
    missing = attach_retrieval(records, traces)

    assert missing == 1
    assert records[0]["retrieved_documents"] == ["a.pdf"]
    assert records[0]["retrieved_chunk_ids"] == ["c1"]
    assert records[1]["retrieved_documents"] == []


def test_attach_retrieval_records_strategy_and_groups() -> None:
    traces = {
        "conv-1": [
            {"retrieval_mode": "hybrid", "rerank_strategy": "llm", "searches": []},
            {"retrieval_mode": "keyword", "rerank_strategy": "off", "searches": []},
        ]
    }
    records = [{"conversation_id": "conv-1"}, {"conversation_id": "conv-2"}]

    attach_retrieval(records, traces)

    # 取最近一条轨迹，代表本轮实际生效的配置。
    assert records[0]["retrieval_mode"] == "keyword"
    assert records[0]["rerank_strategy"] == "off"
    assert set(strategy_groups(records)) == {"keyword/off", "未知/未知"}
