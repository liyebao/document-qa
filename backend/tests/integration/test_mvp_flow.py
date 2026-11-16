import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="需要设置 TEST_DATABASE_URL 指向带 pgvector 的测试数据库",
    ),
]


@pytest.fixture(scope="module")
def client():
    import app.models  # noqa: F401
    from app.db.base import Base
    from app.db.session import engine

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    with engine.begin() as connection:
        Base.metadata.drop_all(connection)


@pytest.fixture(autouse=True)
def _clean_user_data(client):
    """单用户模式共享一个本地用户，每个测试前清理业务数据，避免配置/限流互相影响。"""
    from app.core.ratelimit import ask_limiter, reindex_limiter, upload_limiter
    from app.db.session import engine

    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE processing_jobs, citations, messages, conversations, "
                "chunks, chunk_terms, documents, collections, model_provider_configs "
                "RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(
            text(
                "UPDATE users SET preferred_embedding_provider = NULL, "
                "preferred_chat_provider = NULL"
            )
        )
    for limiter in (ask_limiter, upload_limiter, reindex_limiter):
        limiter.reset()
    yield


def _register(client: TestClient, email: str) -> str:
    """兼容旧测试签名；单用户模式没有注册流程，所有请求自动归属本地用户。"""
    return ""


def _headers(token: str) -> dict[str, str]:
    return {}


def test_upload_ask_citation_and_delete_flow(client: TestClient, monkeypatch) -> None:
    token = _register(client, "flow@example.com")
    headers = _headers(token)

    saved = client.post(
        "/api/settings/model-providers",
        json={
            "provider_key": "openai",
            "api_key": "sk-test-1234567890",
            "embedding_model": "text-embedding-3-small",
            "chat_model": "gpt-4o-mini",
        },
        headers=headers,
    )
    assert saved.status_code == 200, saved.text

    collection = client.post(
        "/api/collections", json={"name": "流程资料"}, headers=headers
    )
    collection_id = collection.json()["id"]

    def fake_embed(_config, texts):
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    monkeypatch.setattr("app.services.embeddings.embed_texts", fake_embed)

    upload = client.post(
        f"/api/collections/{collection_id}/documents",
        files={
            "file": (
                "note.md",
                "# 项目风险\n\n项目存在进度风险，需要提前准备资源。".encode(),
                "text/markdown",
            )
        },
        headers=headers,
    )
    assert upload.status_code == 202, upload.text
    document_id = upload.json()["id"]

    documents = client.get(
        f"/api/collections/{collection_id}/documents", headers=headers
    ).json()
    assert documents[0]["status"] == "ready"

    original = client.get(f"/api/documents/{document_id}/file", headers=headers)
    assert original.status_code == 200
    assert original.headers["content-type"].startswith("text/plain")
    assert "项目存在进度风险" in original.text

    conversation = client.post(
        f"/api/collections/{collection_id}/conversations",
        json={},
        headers=headers,
    ).json()

    tool_calls = {"count": 0}

    def fake_chat_with_tools(*args, **kwargs):
        tool_calls["count"] += 1
        if tool_calls["count"] == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "search_documents",
                            "arguments": '{"query":"项目风险"}',
                        },
                    }
                ],
            }
        return {"content": "READY"}

    monkeypatch.setattr(
        "app.services.model_provider.chat_with_tools", fake_chat_with_tools
    )
    monkeypatch.setattr(
        "app.services.model_provider.chat_completion",
        lambda *args, **kwargs: "项目存在进度风险[1]。",
    )

    answer = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "项目风险是什么？"},
        headers=headers,
    )
    assert answer.status_code == 200, answer.text
    assert tool_calls["count"] >= 1
    assistant = answer.json()["assistant_message"]
    assert assistant["status"] == "completed"
    assert assistant["citations"]
    assert assistant["citations"][0]["document_name"] == "note.md"
    assert assistant["citations"][0]["document_id"] == document_id
    assert "[1]" in assistant["content"]

    deleted = client.delete(f"/api/documents/{document_id}", headers=headers)
    assert deleted.status_code == 204
    assert (
        client.get(f"/api/documents/{document_id}/file", headers=headers).status_code
        == 404
    )

    after_delete = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "还有哪些风险？"},
        headers=headers,
    )
    assert after_delete.status_code == 200, after_delete.text
    assert after_delete.json()["assistant_message"]["status"] == "insufficient"


def _save_provider(
    client: TestClient,
    headers: dict[str, str],
    embedding_model: str = "text-embedding-3-small",
) -> dict:
    response = client.post(
        "/api/settings/model-providers",
        json={
            "provider_key": "openai",
            "api_key": "sk-test-1234567890",
            "embedding_model": embedding_model,
            "chat_model": "gpt-4o-mini",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_collection(
    client: TestClient, headers: dict[str, str], name: str = "资料"
) -> dict:
    response = client.post("/api/collections", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _upload_markdown(
    client: TestClient,
    headers: dict[str, str],
    collection_id: str,
    content: str,
    filename: str = "note.md",
) -> dict:
    response = client.post(
        f"/api/collections/{collection_id}/documents",
        files={"file": (filename, content.encode(), "text/markdown")},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    return response.json()


def _fake_embedding(dimension: int = 4):
    def fake(_config, texts):
        return [[0.1, 0.2, 0.3, 0.4][:dimension] for _ in texts]

    return fake


def test_reindex_switches_embedding_dimension(client: TestClient, monkeypatch) -> None:
    token = _register(client, f"reindex-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)
    _save_provider(client, headers)

    def fake_embed(config, texts):
        dimension = 6 if config.embedding_model == "custom-embed" else 4
        return [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6][:dimension] for _ in texts]

    monkeypatch.setattr("app.services.embeddings.embed_texts", fake_embed)
    collection = _create_collection(client, headers, "重建索引资料集")
    _upload_markdown(client, headers, collection["id"], "# 索引\n\n旧向量内容。")

    current = client.get(f"/api/collections/{collection['id']}", headers=headers)
    assert current.json()["embedding_dimension"] == 4

    updated = client.post(
        "/api/settings/model-providers",
        json={"provider_key": "openai", "embedding_model": "custom-embed"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text

    reindexed = client.post(
        f"/api/collections/{collection['id']}/reindex", json={}, headers=headers
    )
    assert reindexed.status_code == 200, reindexed.text
    payload = reindexed.json()
    assert payload["embedding_dimension"] == 6
    assert payload["index_version"] == 2
    assert payload["chunk_count"] >= 1

    empty = _create_collection(client, headers, "空资料集")
    empty_reindex = client.post(
        f"/api/collections/{empty['id']}/reindex", json={}, headers=headers
    )
    assert empty_reindex.status_code == 409
    assert empty_reindex.json()["error"]["code"] == "REINDEX_EMPTY"

    missing_provider = client.post(
        f"/api/collections/{collection['id']}/reindex",
        json={"provider_key": "not-exists"},
        headers=headers,
    )
    assert missing_provider.status_code == 422
    assert missing_provider.json()["error"]["code"] == "MODEL_NOT_CONFIGURED"


def test_replace_disable_and_chunk_cleanup(client: TestClient, monkeypatch) -> None:
    token = _register(client, f"replace-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)
    _save_provider(client, headers)
    monkeypatch.setattr(
        "app.services.embeddings.embed_texts", _fake_embedding(4)
    )
    monkeypatch.setattr(
        "app.services.model_provider.chat_with_tools",
        lambda *args, **kwargs: {"content": "READY"},
    )
    monkeypatch.setattr(
        "app.services.model_provider.chat_completion",
        lambda *args, **kwargs: "新版本内容说明[1]。",
    )

    collection = _create_collection(client, headers, "版本资料集")
    old = _upload_markdown(
        client, headers, collection["id"], "# 项目风险\n\n旧版本内容。"
    )
    replaced = client.post(
        f"/api/documents/{old['id']}/replace",
        files={"file": ("note.md", "# 项目风险\n\n新版本内容。".encode(), "text/markdown")},
        headers=headers,
    )
    assert replaced.status_code == 202, replaced.text
    new = replaced.json()
    assert new["version"] == 2

    documents = client.get(
        f"/api/collections/{collection['id']}/documents", headers=headers
    ).json()
    assert len(documents) == 1
    assert documents[0]["version"] == 2

    from app.db.session import SessionLocal
    from app.models.chunk import Chunk

    with SessionLocal() as db:
        old_chunks = db.scalars(
            select(Chunk).where(Chunk.document_id == uuid.UUID(old["id"]))
        ).all()
    assert old_chunks == []

    not_current = client.post(
        f"/api/documents/{old['id']}/replace",
        files={"file": ("note.md", "# 项目风险\n\n再次替换。".encode(), "text/markdown")},
        headers=headers,
    )
    assert not_current.status_code == 409
    assert not_current.json()["error"]["code"] == "DOCUMENT_NOT_CURRENT"

    retry = client.post(f"/api/documents/{new['id']}/retry", headers=headers)
    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "DOCUMENT_NOT_FAILED"

    disabled = client.patch(
        f"/api/documents/{new['id']}", json={"is_enabled": False}, headers=headers
    )
    assert disabled.status_code == 200

    conversation = client.post(
        f"/api/collections/{collection['id']}/conversations",
        json={},
        headers=headers,
    ).json()
    disabled_answer = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "项目风险是什么？"},
        headers=headers,
    )
    assert disabled_answer.status_code == 200
    assert disabled_answer.json()["assistant_message"]["status"] == "insufficient"

    enabled = client.patch(
        f"/api/documents/{new['id']}", json={"is_enabled": True}, headers=headers
    )
    assert enabled.status_code == 200
    enabled_answer = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "项目风险是什么？"},
        headers=headers,
    )
    assert enabled_answer.status_code == 200, enabled_answer.text
    assistant = enabled_answer.json()["assistant_message"]
    assert assistant["status"] == "completed"
    assert assistant["citations"]


def test_upload_validation_and_duplicate(client: TestClient, monkeypatch) -> None:
    token = _register(client, f"validate-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)
    _save_provider(client, headers)
    monkeypatch.setattr(
        "app.services.embeddings.embed_texts", _fake_embedding(4)
    )
    collection = _create_collection(client, headers, "校验资料集")

    content = "# 标题\n\n重复内容。"
    _upload_markdown(client, headers, collection["id"], content)
    duplicate = client.post(
        f"/api/collections/{collection['id']}/documents",
        files={"file": ("note.md", content.encode(), "text/markdown")},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_FILE"

    invalid_pdf = client.post(
        f"/api/collections/{collection['id']}/documents",
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        headers=headers,
    )
    assert invalid_pdf.status_code == 415
    assert invalid_pdf.json()["error"]["code"] == "UNSUPPORTED_FORMAT"

    empty = client.post(
        f"/api/collections/{collection['id']}/documents",
        files={"file": ("empty.md", b"", "text/markdown")},
        headers=headers,
    )
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "EMPTY_FILE"

    unsupported = client.post(
        f"/api/collections/{collection['id']}/documents",
        files={"file": ("note.bin", b"hello", "application/octet-stream")},
        headers=headers,
    )
    assert unsupported.status_code == 415


def test_input_validation_and_origin_guard(client: TestClient) -> None:
    token = _register(client, f"input-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)

    blank_name = client.post(
        "/api/collections", json={"name": "   "}, headers=headers
    )
    assert blank_name.status_code == 422

    collection = _create_collection(client, headers, "输入校验")
    conversation = client.post(
        f"/api/collections/{collection['id']}/conversations",
        json={"title": "   "},
        headers=headers,
    )
    assert conversation.status_code == 201
    assert conversation.json()["title"] == "新会话"

    blank_question = client.post(
        f"/api/conversations/{conversation.json()['id']}/messages",
        json={"content": "   "},
        headers=headers,
    )
    assert blank_question.status_code == 422

    rejected = client.post(
        "/api/collections",
        json={"name": "跨站请求"},
        headers={**headers, "Origin": "http://evil.example"},
    )
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "ORIGIN_REJECTED"

    assert (
        client.get("/api/collections", headers={**headers, "Origin": "http://evil.example"})
        .status_code
        == 200
    )


def test_failed_answer_is_recorded_in_history(client: TestClient, monkeypatch) -> None:
    from app.core.errors import AppError

    token = _register(client, f"failure-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)
    _save_provider(client, headers)
    monkeypatch.setattr(
        "app.services.embeddings.embed_texts", _fake_embedding(4)
    )
    monkeypatch.setattr(
        "app.services.model_provider.chat_with_tools",
        lambda *args, **kwargs: {"content": "READY"},
    )

    def failing_chat(*args, **kwargs):
        raise AppError("MODEL_PROVIDER_ERROR", "模型服务不可用", 502)

    monkeypatch.setattr("app.services.model_provider.chat_completion", failing_chat)

    collection = _create_collection(client, headers, "失败记录资料集")
    _upload_markdown(client, headers, collection["id"], "# 资料\n\n失败测试内容。")
    conversation = client.post(
        f"/api/collections/{collection['id']}/conversations",
        json={},
        headers=headers,
    ).json()

    failed = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "项目风险是什么？"},
        headers=headers,
    )
    assert failed.status_code == 502

    detail = client.get(
        f"/api/conversations/{conversation['id']}", headers=headers
    ).json()
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["status"] == "failed"


def test_saving_provider_sets_requested_role(client: TestClient) -> None:
    token = _register(client, f"save-role-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)

    chat = client.post(
        "/api/settings/model-providers",
        json={
            "provider_key": "openai",
            "api_key": "sk-chat-only",
            "role": "chat",
            "chat_model": "gpt-4o-mini",
        },
        headers=headers,
    )
    assert chat.status_code == 200, chat.text
    assert chat.json()["embedding_model"] == ""
    assert chat.json()["is_chat_default"] is True
    assert chat.json()["is_embedding_default"] is False

    embedding = client.post(
        "/api/settings/model-providers",
        json={
            "provider_key": "dashscope",
            "api_key": "sk-embedding-only",
            "role": "embedding",
            "embedding_model": "text-embedding-v4",
        },
        headers=headers,
    )
    assert embedding.status_code == 200, embedding.text
    assert embedding.json()["is_embedding_default"] is True

    settings = client.get("/api/settings/model-providers", headers=headers).json()
    assert settings["preferred_chat_provider"] == "openai"
    assert settings["preferred_embedding_provider"] == "dashscope"

    both = client.post(
        "/api/settings/model-providers",
        json={
            "provider_key": "siliconflow",
            "api_key": "sk-both",
            "role": "both",
            "embedding_model": "BAAI/bge-m3",
            "chat_model": "Qwen/Qwen3-8B",
        },
        headers=headers,
    )
    assert both.status_code == 200, both.text
    settings = client.get("/api/settings/model-providers", headers=headers).json()
    assert settings["preferred_chat_provider"] == "siliconflow"
    assert settings["preferred_embedding_provider"] == "siliconflow"

    rejected = client.post(
        "/api/settings/model-providers",
        json={
            "provider_key": "deepseek",
            "api_key": "sk-no-embedding",
            "role": "both",
            "chat_model": "deepseek-chat",
        },
        headers=headers,
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "UNSUPPORTED_PROVIDER"

    settings = client.get("/api/settings/model-providers", headers=headers).json()
    assert settings["effective_embedding"]["provider_key"] == "siliconflow"
    assert settings["effective_chat"]["provider_key"] == "siliconflow"

    # 编辑已有配置且不传 role 时，不能抢占当前生效的检索/回答模型。
    updated = client.post(
        "/api/settings/model-providers",
        json={
            "provider_key": "openai",
            "embedding_model": "text-embedding-3-small",
            "chat_model": "gpt-4o-mini",
        },
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    settings = client.get("/api/settings/model-providers", headers=headers).json()
    assert settings["preferred_embedding_provider"] == "siliconflow"
    assert settings["preferred_chat_provider"] == "siliconflow"


def test_chat_only_connection_test_does_not_require_embedding(
    client: TestClient, monkeypatch
) -> None:
    token = _register(client, f"chat-only-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)
    saved = client.post(
        "/api/settings/model-providers",
        json={
            "provider_key": "openai",
            "api_key": "sk-chat-only",
            "role": "chat",
            "chat_model": "gpt-4o-mini",
        },
        headers=headers,
    ).json()
    monkeypatch.setattr(
        "app.services.model_provider.chat_completion",
        lambda *args, **kwargs: "连接成功",
    )

    result = client.post(
        f"/api/settings/model-providers/{saved['id']}/test",
        json={},
        headers=headers,
    )

    assert result.status_code == 200, result.text
    assert result.json()["ok"] is True
    assert result.json()["embedding_ok"] is False
    assert result.json()["chat_ok"] is True


def test_connection_test_validates_embedding_dimension(
    client: TestClient, monkeypatch
) -> None:
    token = _register(client, f"dimension-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)
    saved = client.post(
        "/api/settings/model-providers",
        json={
            "provider_key": "dashscope",
            "api_key": "sk-test",
            "embedding_model": "text-embedding-v4",
            "chat_model": "qwen-max",
        },
        headers=headers,
    ).json()

    def fake_embedding(_spec, _key, _model, texts):
        return [[0.0] * 1024 for _ in texts]

    monkeypatch.setattr(
        "app.services.model_provider.request_embeddings", fake_embedding
    )
    monkeypatch.setattr(
        "app.services.model_provider.chat_completion",
        lambda *args, **kwargs: "连接成功",
    )

    result = client.post(
        f"/api/settings/model-providers/{saved['id']}/test",
        json={},
        headers=headers,
    )

    assert result.status_code == 200, result.text
    assert result.json()["ok"] is True
    assert "1024 维" in result.json()["message"]
    assert "已建立 HNSW 索引" in result.json()["message"]


def test_embedding_and_chat_can_use_different_providers(client: TestClient) -> None:
    token = _register(client, f"roles-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)
    openai = _save_provider(client, headers)
    deepseek = client.post(
        "/api/settings/model-providers",
        json={
            "provider_key": "deepseek",
            "api_key": "sk-deepseek-test",
            "embedding_model": "",
            "chat_model": "deepseek-chat",
        },
        headers=headers,
    )
    assert deepseek.status_code == 200, deepseek.text
    deepseek_config = deepseek.json()

    # 新增回答服务商不会抢占已有的检索/回答默认项。
    settings = client.get("/api/settings/model-providers", headers=headers).json()
    assert settings["preferred_embedding_provider"] == "openai"
    assert settings["preferred_chat_provider"] == "openai"

    chat_role = client.post(
        f"/api/settings/model-providers/{deepseek_config['id']}/role",
        json={"role": "chat"},
        headers=headers,
    )
    assert chat_role.status_code == 200, chat_role.text
    assert chat_role.json()["preferred_chat_provider"] == "deepseek"
    assert chat_role.json()["preferred_embedding_provider"] == "openai"

    rejected = client.post(
        f"/api/settings/model-providers/{deepseek_config['id']}/role",
        json={"role": "embedding"},
        headers=headers,
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "MODEL_NOT_CONFIGURED"

    assert openai["provider_key"] == "openai"


def test_stale_processing_documents_are_recovered(client: TestClient) -> None:
    token = _register(client, f"stale-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)
    collection = _create_collection(client, headers, "任务恢复资料集")

    from app.db.session import SessionLocal
    from app.models.document import DOCUMENT_STATUS_PROCESSING, Document
    from app.services.ingestion import mark_stale_documents_failed

    with SessionLocal() as db:
        document = Document(
            collection_id=uuid.UUID(collection["id"]),
            filename="stale.md",
            format="md",
            checksum=uuid.uuid4().hex,
            version=1,
            status=DOCUMENT_STATUS_PROCESSING,
            storage_path="storage/uploads/stale.md",
        )
        db.add(document)
        db.commit()
        document_id = document.id

    assert mark_stale_documents_failed() >= 1
    with SessionLocal() as db:
        recovered = db.get(Document, document_id)
        assert recovered.status == "failed"
        assert recovered.failure_reason

    client.delete(f"/api/documents/{document_id}", headers=headers)


def test_document_scope_filtering(client: TestClient, monkeypatch) -> None:
    token = _register(client, f"scope-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)
    _save_provider(client, headers)
    monkeypatch.setattr("app.services.embeddings.embed_texts", _fake_embedding(4))
    monkeypatch.setattr(
        "app.services.model_provider.chat_with_tools",
        lambda *args, **kwargs: {"content": "READY"},
    )
    monkeypatch.setattr(
        "app.services.model_provider.chat_completion",
        lambda *args, **kwargs: "苹果是一种水果。[1]",
    )

    collection = _create_collection(client, headers, "范围资料集")
    first = _upload_markdown(
        client, headers, collection["id"], "# A\n\n苹果是一种水果。", "a.md"
    )
    _upload_markdown(
        client, headers, collection["id"], "# B\n\n香蕉是一种水果。", "b.md"
    )
    from app.db.session import SessionLocal
    from app.services.local_user import get_local_user
    from app.services.retrieval.bm25 import bm25_search

    with SessionLocal() as db:
        local_user_id = get_local_user(db).id
        hits = bm25_search(
            db,
            collection_id=uuid.UUID(collection["id"]),
            user_id=local_user_id,
            query="水果",
            limit=10,
        )
    assert hits

    conversation = client.post(
        f"/api/collections/{collection['id']}/conversations", json={}, headers=headers
    ).json()

    scoped = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "有哪些水果？", "document_ids": [first["id"]]},
        headers=headers,
    )
    assert scoped.status_code == 200, scoped.text
    citations = scoped.json()["assistant_message"]["citations"]
    assert citations
    assert {item["document_id"] for item in citations} == {first["id"]}

    mismatch = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "b.md 讲了什么？", "document_ids": [first["id"]]},
        headers=headers,
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "DOCUMENT_SCOPE_MISMATCH"

    other_collection = _create_collection(client, headers, "另一个资料集")
    other_document = _upload_markdown(
        client, headers, other_collection["id"], "# C\n\n另一个资料集的内容。", "c.md"
    )
    invalid = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"content": "有哪些水果？", "document_ids": [other_document["id"]]},
        headers=headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_DOCUMENT_SCOPE"


def test_new_document_sources(client: TestClient, monkeypatch) -> None:
    token = _register(client, f"sources-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)
    _save_provider(client, headers)
    monkeypatch.setattr("app.services.embeddings.embed_texts", _fake_embedding(4))
    collection = _create_collection(client, headers, "多源资料集")

    text_document = client.post(
        f"/api/collections/{collection['id']}/documents/text",
        json={"title": "会议纪要", "content": "预算需要复核。\n\n进度风险可控。"},
        headers=headers,
    )
    assert text_document.status_code == 202, text_document.text
    assert text_document.json()["source_type"] == "text"

    txt_document = client.post(
        f"/api/collections/{collection['id']}/documents",
        files={"file": ("plain.txt", "纯文本内容。".encode(), "text/plain")},
        headers=headers,
    )
    assert txt_document.status_code == 202, txt_document.text
    assert txt_document.json()["format"] == "txt"

    blocked = client.post(
        f"/api/collections/{collection['id']}/documents/url",
        json={"url": "http://127.0.0.1:8080/private"},
        headers=headers,
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "URL_FORBIDDEN"

    documents = client.get(
        f"/api/collections/{collection['id']}/documents", headers=headers
    ).json()
    assert all(item["status"] == "ready" for item in documents)


def test_processing_jobs_queue(client: TestClient) -> None:
    token = _register(client, f"jobs-{uuid.uuid4().hex[:8]}@example.com")
    headers = _headers(token)
    collection = _create_collection(client, headers, "任务队列资料集")

    from app.db.session import SessionLocal
    from app.models.document import DOCUMENT_STATUS_PROCESSING, Document
    from app.services import jobs

    with SessionLocal() as db:
        document = Document(
            collection_id=uuid.UUID(collection["id"]),
            filename="queue.md",
            format="md",
            checksum=uuid.uuid4().hex,
            version=1,
            status=DOCUMENT_STATUS_PROCESSING,
            storage_path="storage/uploads/queue.md",
        )
        db.add(document)
        db.commit()
        document_id = document.id

    with SessionLocal() as db:
        job = jobs.enqueue(db, document_id)
        db.commit()
        job_id = job.id

        duplicate = jobs.enqueue(db, document_id)
        db.commit()
        assert duplicate.id == job_id

        claimed = jobs.claim_next(db, "worker-test")
        assert claimed is not None
        assert claimed.id == job_id
        assert claimed.status == "running"
        assert claimed.attempts == 1

        jobs.mark_failed(db, claimed, "模拟失败")
        assert claimed.status == "pending"
        # 退避期内不可再次领取
        assert jobs.claim_next(db, "worker-test") is None

        from datetime import UTC, datetime, timedelta

        claimed.run_after = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

        claimed_again = jobs.claim_next(db, "worker-test")
        assert claimed_again is not None
        jobs.mark_succeeded(db, claimed_again)
        assert claimed_again.status == "succeeded"

        assert jobs.reap_stale(db, 0) == 0
