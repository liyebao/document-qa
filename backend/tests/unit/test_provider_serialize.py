import base64
import uuid
from datetime import UTC, datetime

from app.core.secrets import encrypt_secret
from app.models.model_provider_config import ModelProviderConfig
from app.services.model_provider import serialize_config


def _config(ciphertext: str, key_version: int = 1) -> ModelProviderConfig:
    return ModelProviderConfig(
        id=uuid.uuid4(),
        provider_key="openai",
        embedding_model="text-embedding-3-small",
        chat_model="gpt-4o-mini",
        rerank_model=None,
        status="ok",
        api_key_ciphertext=ciphertext,
        key_version=key_version,
        last_tested_at=None,
        updated_at=datetime.now(UTC),
    )


def test_short_key_keeps_status_and_masks_fully() -> None:
    """长度 ≤8 的密钥脱敏后就是 '****'，不能被当成「解不开」。"""
    ciphertext, key_version = encrypt_secret("shortkey")

    out = serialize_config(_config(ciphertext, key_version))

    assert out.key_masked == "****"
    assert out.status == "ok"


def test_undecryptable_ciphertext_reports_key_unreadable() -> None:
    old_key = base64.urlsafe_b64encode(b"q" * 32).decode()
    ciphertext, key_version = encrypt_secret("sk-lost-after-rotation", key=old_key, key_version=1)

    out = serialize_config(_config(ciphertext, key_version))

    assert out.key_masked == "****"
    assert out.status == "key_unreadable"
