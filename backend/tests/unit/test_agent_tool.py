from types import SimpleNamespace

from app.core.errors import AppError
from app.services.agent_tools import (
    MAX_TOOL_QUERY_CHARS,
    _parse_tool_query,
    _run_tool_loop,
)


class FakeAgent:
    def __init__(self) -> None:
        self.searches: list[tuple[str, int]] = []

    def search_documents(self, query: str, *, query_index: int = 0) -> list:
        self.searches.append((query, query_index))
        return []

    def format_search_preview(self, chunk_ids: list, limit: int = 3) -> str:
        return ""


def _tool_call(
    *,
    name: str = "search_documents",
    arguments: str = '{"query":"项目风险"}',
    call_id: str = "call_1",
) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def test_parse_tool_query_accepts_json_and_dict() -> None:
    assert _parse_tool_query('{"query": "  项目   风险 "}') == "项目 风险"
    assert _parse_tool_query({"query": "进度风险"}) == "进度风险"


def test_parse_tool_query_rejects_invalid_arguments() -> None:
    assert _parse_tool_query("not-json") is None
    assert _parse_tool_query("[]") is None
    assert _parse_tool_query('{"query": ""}') is None
    assert _parse_tool_query('{"query": 123}') is None
    assert _parse_tool_query({"query": "x" * (MAX_TOOL_QUERY_CHARS + 1)}) is None


def test_tool_loop_rejects_unsupported_tool(monkeypatch) -> None:
    agent = FakeAgent()

    def fake_chat(_config, _messages, _tools):
        return {"tool_calls": [_tool_call(name="delete_all")]}

    monkeypatch.setattr("app.services.agent_tools._chat_with_tools", fake_chat)
    stats, executed = _run_tool_loop(
        agent, object(), "项目有哪些风险？", [], ["项目风险"]
    )

    assert agent.searches == []
    assert stats == {"tool_rounds": 3, "retrieval_calls": 0, "fallback": 0}
    assert executed == {}


def test_tool_loop_rejects_bad_arguments(monkeypatch) -> None:
    agent = FakeAgent()

    def fake_chat(_config, _messages, _tools):
        return {"tool_calls": [_tool_call(arguments="{}")]}

    monkeypatch.setattr("app.services.agent_tools._chat_with_tools", fake_chat)
    stats, executed = _run_tool_loop(
        agent, object(), "项目有哪些风险？", [], ["项目风险"]
    )

    assert agent.searches == []
    assert stats["retrieval_calls"] == 0
    assert executed == {}


def test_tool_loop_enforces_retrieval_limit(monkeypatch) -> None:
    agent = FakeAgent()
    monkeypatch.setattr(
        "app.services.agent_tools.get_settings",
        lambda: SimpleNamespace(agent_max_tool_rounds=1, agent_max_tool_calls=1),
    )

    def fake_chat(_config, _messages, _tools):
        return {
            "tool_calls": [
                _tool_call(arguments='{"query":"进度风险"}', call_id="call_1"),
                _tool_call(arguments='{"query":"资源风险"}', call_id="call_2"),
            ]
        }

    monkeypatch.setattr("app.services.agent_tools._chat_with_tools", fake_chat)
    stats, executed = _run_tool_loop(
        agent, object(), "项目有哪些风险？", [], ["进度风险", "资源风险"]
    )

    assert agent.searches == [("进度风险", 0)]
    assert stats["retrieval_calls"] == 1
    assert executed == {"进度风险": 0}


def test_tool_loop_falls_back_when_tools_unsupported(monkeypatch) -> None:
    agent = FakeAgent()

    def fake_chat(_config, _messages, _tools):
        raise AppError("MODEL_PROVIDER_ERROR", "不支持工具调用", 502)

    monkeypatch.setattr("app.services.agent_tools._chat_with_tools", fake_chat)
    stats, executed = _run_tool_loop(
        agent, object(), "项目有哪些风险？", [], ["项目风险"]
    )

    assert stats == {"tool_rounds": 0, "retrieval_calls": 0, "fallback": 1}
    assert executed == {}
