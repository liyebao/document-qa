from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.services.answering import SYSTEM_PROMPT
from app.services.conversations import _message_out
from app.services.trace import build_retrieval_trace


def _chunk(page_start: int | None, page_end: int | None = None, heading_path: str = ""):
    return SimpleNamespace(
        page_start=page_start, page_end=page_end, heading_path=heading_path
    )


def test_build_retrieval_trace_dedupes_queries_and_documents() -> None:
    agent = SimpleNamespace(
        traces=[
            SimpleNamespace(query="  七步全景 ", query_index=0),
            SimpleNamespace(query="七步全景", query_index=-1),
            SimpleNamespace(query="检索策略", query_index=1),
        ],
        evidence=[
            SimpleNamespace(
                index=1,
                document=SimpleNamespace(filename="资料A.pdf"),
                chunk=_chunk(1, 2),
            ),
            SimpleNamespace(
                index=2,
                document=SimpleNamespace(filename="资料A.pdf"),
                chunk=_chunk(1, 2),
            ),
            SimpleNamespace(
                index=3,
                document=SimpleNamespace(filename="资料B.docx"),
                chunk=_chunk(None, heading_path="第2章 > 2.1 风险"),
            ),
        ],
    )

    payload = build_retrieval_trace(agent)

    assert payload["queries"] == ["七步全景", "检索策略"]
    assert payload["searches"] == 3
    assert payload["expanded"] == 1
    assert payload["full_scan_chunks"] == 0
    assert payload["documents"] == [
        {"name": "资料A.pdf", "location": "第 1–2 页", "marker": 1},
        {"name": "资料B.docx", "location": "2.1 风险", "marker": 3},
    ]


def test_message_out_keeps_retrieval_trace() -> None:
    message = SimpleNamespace(
        id=uuid4(),
        role="assistant",
        content="回答",
        status="completed",
        created_at=datetime.now(UTC),
        retrieval_trace={"queries": ["检索词"], "documents": [], "searches": 1, "expanded": 0},
    )

    result = _message_out(message, [])

    assert result.retrieval_trace == message.retrieval_trace


def test_system_prompt_requires_answer_template() -> None:
    assert "结论" in SYSTEM_PROMPT
    assert "依据" in SYSTEM_PROMPT
    assert "补充说明" in SYSTEM_PROMPT
    assert "以上信息来自" in SYSTEM_PROMPT
    assert "当前资料无法确认" in SYSTEM_PROMPT
    assert "禁止出现「片段」" in SYSTEM_PROMPT
    assert "关联问题" in SYSTEM_PROMPT
