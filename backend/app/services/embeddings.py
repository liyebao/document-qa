from app.core.config import get_settings
from app.core.secrets import decrypt_secret
from app.models.model_provider_config import ModelProviderConfig
from app.services import model_provider


def embed_texts(config: ModelProviderConfig, texts: list[str]) -> list[list[float]]:
    """按批调用 Embedding 服务；密钥只在后端解密使用。"""
    if not texts:
        return []
    spec = model_provider.get_provider_spec(config.provider_key)
    api_key = decrypt_secret(config.api_key_ciphertext, config.key_version)
    # 不同服务商对单次 input 数量限制不同（如百炼 text-embedding-v4 仅 10 条），
    # 取全局批大小与服务商上限的较小值，避免大批文件处理到中途才失败。
    batch_size = max(1, min(get_settings().embedding_batch_size, spec.max_embedding_batch))
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(model_provider.request_embeddings(spec, api_key, config.embedding_model, batch))
    return vectors
