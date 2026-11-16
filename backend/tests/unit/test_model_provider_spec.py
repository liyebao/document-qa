import pytest

from app.core.errors import AppError
from app.services.model_provider import get_provider_spec, list_providers


def test_provider_list_exposes_expected_capabilities() -> None:
    providers = {item.key: item for item in list_providers()}

    assert providers["openai"].requires_api_key is True
    assert providers["ollama"].requires_api_key is False
    assert providers["deepseek"].embedding_models == []
    assert providers["openai"].embedding_models
    assert providers["openai"].chat_models
    assert providers["siliconflow"].rerank_models
    assert providers["openai"].rerank_models == []


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(AppError) as exc:
        get_provider_spec("not-exist")
    assert exc.value.code == "UNSUPPORTED_PROVIDER"
