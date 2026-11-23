import base64
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings
from app.core.errors import AppError

_NONCE_SIZE = 12
logger = logging.getLogger(__name__)


def _decode_key(raw: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(raw)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY 必须是 base64 编码的 32 字节密钥") from exc
    if len(key) != 32:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY 必须是 base64 编码的 32 字节密钥")
    return key


def _load_key(raw: str | None = None) -> bytes:
    return _decode_key(raw if raw is not None else get_settings().credential_encryption_key)


def encrypt_secret(
    plaintext: str,
    *,
    key: str | None = None,
    key_version: int | None = None,
) -> tuple[str, int]:
    """使用 AES-GCM 加密用户 API Key，返回密文与密钥版本。

    `key` / `key_version` 仅供轮换脚本使用；业务调用使用当前环境配置。
    """
    settings = get_settings()
    version = settings.credential_key_version if key_version is None else key_version
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(_load_key(key)).encrypt(nonce, plaintext.encode("utf-8"), b"")
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii"), version


def decrypt_secret(
    ciphertext: str,
    key_version: int,
    *,
    key: str | None = None,
) -> str:
    if key is None and key_version != get_settings().credential_key_version:
        raise RuntimeError(
            "密钥版本与当前 CREDENTIAL_ENCRYPTION_KEY_VERSION 不一致，"
            "请先运行密钥轮换脚本"
        )
    raw = base64.urlsafe_b64decode(ciphertext)
    plaintext = AESGCM(_load_key(key)).decrypt(raw[:_NONCE_SIZE], raw[_NONCE_SIZE:], b"")
    return plaintext.decode("utf-8")


def read_secret(ciphertext: str, key_version: int) -> str:
    """业务侧解密入口：解不开时给出可操作的 409，而不是 500。

    常见成因是 CREDENTIAL_ENCRYPTION_KEY 被替换（或 .env 被覆盖），旧密文
    已无法还原。此时唯一正确的处理是让用户重新填写并保存该配置，因此这里
    把 cryptography 的 InvalidTag、版本不一致、base64 损坏统一转成
    CREDENTIAL_UNREADABLE，避免前端只看到「系统内部错误」。
    """
    try:
        return decrypt_secret(ciphertext, key_version)
    except Exception as exc:  # noqa: BLE001  解密失败原因对用户没有意义
        logger.warning(
            "凭据解密失败，key_version=%s，原因=%s", key_version, type(exc).__name__
        )
        raise AppError(
            "CREDENTIAL_UNREADABLE",
            "已保存的 API Key 无法解密（主密钥已更换或版本不匹配），"
            "请在设置页重新填写该模型配置并保存",
            409,
        ) from exc


def reencrypt_secret(
    ciphertext: str,
    *,
    old_key: str,
    old_version: int,
    new_key: str,
    new_version: int,
) -> tuple[str, int]:
    """把一条密文从旧主密钥迁移到新主密钥。"""
    plaintext = decrypt_secret(ciphertext, old_version, key=old_key)
    return encrypt_secret(plaintext, key=new_key, key_version=new_version)


def mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return "****"
    return f"{secret[:3]}****{secret[-4:]}"
