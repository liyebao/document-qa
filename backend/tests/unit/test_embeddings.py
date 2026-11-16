from app.core.secrets import encrypt_secret
from app.models.model_provider_config import ModelProviderConfig
from app.services import embeddings, model_provider


def _config(provider_key: str, embedding_model: str) -> ModelProviderConfig:
    ciphertext, version = encrypt_secret("sk-test")
    return ModelProviderConfig(
        user_id=None,
        provider_key=provider_key,
        api_key_ciphertext=ciphertext,
        key_version=version,
        embedding_model=embedding_model,
        chat_model="test",
    )


def test_embedding_batches_respect_provider_limit(monkeypatch) -> None:
    batches: list[int] = []

    def fake_request(_spec, _api_key, _model, texts):
        batches.append(len(texts))
        return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(model_provider, "request_embeddings", fake_request)
    config = _config("dashscope", "text-embedding-v4")

    vectors = embeddings.embed_texts(config, [f"text-{i}" for i in range(21)])

    assert len(vectors) == 21
    assert batches == [10, 10, 1]


def test_zhipu_embedding_requests_1024_dimensions(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(_spec, _key, _path, payload):
        captured.update(payload)
        return {"data": [{"index": 0, "embedding": [0.0] * 1024}]}

    monkeypatch.setattr(model_provider, "_post_json", fake_post)
    spec = model_provider.get_provider_spec("zhipu")

    vectors = model_provider.request_embeddings(
        spec, "sk-test", "embedding-3", ["测试"]
    )

    assert captured["dimensions"] == 1024
    assert len(vectors[0]) == 1024
