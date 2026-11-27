import pytest
from pydantic import ValidationError

from app.schemas.collection import CollectionCreate
from app.schemas.conversation import ConversationCreate, MessageCreate
from app.schemas.settings import ModelProviderConfigCreate
from app.services.model_provider import PROVIDERS, _chat_payload


def test_provider_models_are_optional() -> None:
    payload = ModelProviderConfigCreate(provider_key="openai", api_key="sk-test")
    assert payload.embedding_model is None
    assert payload.chat_model is None


def test_each_provider_has_chat_models() -> None:
    for spec in PROVIDERS.values():
        assert spec.chat_models


def test_deepseek_is_chat_only() -> None:
    spec = PROVIDERS["deepseek"]
    assert spec.embedding_models == ()
    assert "deepseek-flash" in spec.chat_models
    assert "deepseek-chat" not in spec.chat_models


def test_embedding_batch_limits_match_provider_constraints() -> None:
    # 百炼 text-embedding-v4 单次最多 10 条，默认 16 会导致大文件处理失败。
    assert PROVIDERS["dashscope"].max_embedding_batch == 10
    assert PROVIDERS["zhipu"].embedding_dimensions == 1024
    assert PROVIDERS["ollama"].max_embedding_batch == 1


def test_reasoning_chat_payload_omits_unsupported_parameters() -> None:
    spec = PROVIDERS["openai"]
    payload = _chat_payload(
        spec, "gpt-5.1", [{"role": "user", "content": "hi"}], 0.2, 1200
    )
    assert "temperature" not in payload
    assert "max_tokens" not in payload
    assert payload["max_completion_tokens"] == 4096

    normal = _chat_payload(
        spec, "gpt-4o-mini", [{"role": "user", "content": "hi"}], 0.2, 1200
    )
    assert normal["temperature"] == 0.2
    assert normal["max_tokens"] == 1200


def test_qwen_thinking_models_disable_thinking_for_short_answers() -> None:
    payload = _chat_payload(
        PROVIDERS["dashscope"],
        "qwen3.8-max",
        [{"role": "user", "content": "hi"}],
        0.2,
        1200,
    )
    assert payload["reasoning_effort"] == "none"


def test_deepseek_chat_disables_thinking_for_tool_calls() -> None:
    payload = _chat_payload(
        PROVIDERS["deepseek"], "deepseek-v4-pro", [{"role": "user", "content": "hi"}], 0.2, 1200
    )
    assert payload["thinking"] == {"type": "disabled"}


def test_local_provider_does_not_require_api_key() -> None:
    assert PROVIDERS["ollama"].requires_api_key is False
    assert PROVIDERS["openai"].requires_api_key is True


def test_zhipu_provides_embedding_and_chat() -> None:
    spec = PROVIDERS["zhipu"]
    assert "embedding-3" in spec.embedding_models
    assert "glm-4-flash" in spec.chat_models


def test_provider_payload_strips_whitespace() -> None:
    payload = ModelProviderConfigCreate(
        provider_key="  openai  ",
        api_key="   ",
        embedding_model="  text-embedding-3-small  ",
        chat_model="  gpt-4o-mini  ",
    )
    assert payload.provider_key == "openai"
    assert payload.api_key is None
    assert payload.embedding_model == "text-embedding-3-small"
    assert payload.chat_model == "gpt-4o-mini"


def test_blank_collection_name_is_rejected() -> None:
    assert CollectionCreate(name="  资料集  ").name == "资料集"
    with pytest.raises(ValidationError):
        CollectionCreate(name="   ")


def test_blank_question_and_title_are_normalized() -> None:
    with pytest.raises(ValidationError):
        MessageCreate(content="   ")
    assert ConversationCreate(title="   ").title is None
    assert ConversationCreate(title="  标题  ").title == "标题"


def test_credential_key_version_reads_documented_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import Settings

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY_VERSION", "9")
    assert Settings().credential_encryption_key_version == 9
